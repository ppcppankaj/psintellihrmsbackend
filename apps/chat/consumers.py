"""Chat Consumers - Tenant-safe WebSocket handlers."""

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone


class ChatConsumer(AsyncWebsocketConsumer):
    """Real-time chat consumer with tenant isolation and reactions."""

    async def connect(self):
        self.user = self.scope.get("user")
        self.organization = self.scope.get("organization")
        self.organization_id = str(self.organization.id) if self.organization else None
        self.conversation_id = (
            self.scope.get("url_route", {})
            .get("kwargs", {})
            .get("conversation_id")
        )

        if (
            not self.user
            or self.user.is_anonymous
            or not self.organization_id
            or not self.conversation_id
        ):
            await self.close(code=4401)
            return

        if self.scope.get("org_mismatch"):
            await self.close(code=4403)
            return

        conversation = await self.get_conversation()
        if not conversation:
            await self.close(code=4404)
            return

        self.conversation_org_id = str(conversation["organization_id"])
        if self.conversation_org_id != self.organization_id:
            await self.close(code=4403)
            return

        is_participant = await self.is_participant()
        if not is_participant:
            await self.close(code=4403)
            return

        self.room_group_name = f"chat_{self.conversation_id}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_online",
                "user_id": str(self.user.id),
                "username": self._user_display_name(),
            },
        )

    async def disconnect(self, close_code):
        if getattr(self, "room_group_name", None):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_offline",
                    "user_id": str(self.user.id),
                },
            )
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        message_type = data.get("type")
        handler_map = {
            "chat_message": self.handle_chat_message,
            "typing": self.handle_typing,
            "read_receipt": self.handle_read_receipt,
            "add_reaction": self.handle_add_reaction,
        }

        handler = handler_map.get(message_type)
        if handler:
            await handler(data)

    async def handle_chat_message(self, data):
        content = (data.get("content") or "").strip()
        if not content:
            return

        reply_to_id = data.get("reply_to")
        message_payload = await self.save_message(content, reply_to_id=reply_to_id)
        if not message_payload:
            return

        message_payload.update(
            {
                "type": "chat_message",
                "sender_id": str(self.user.id),
                "sender_name": self._user_display_name(),
                "conversation_id": str(self.conversation_id),
            }
        )

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message_payload,
            },
        )

    async def handle_typing(self, data):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "typing_indicator",
                "user_id": str(self.user.id),
                "username": self._user_display_name(),
                "is_typing": bool(data.get("is_typing")),
            },
        )

    async def handle_read_receipt(self, _data):
        await self.update_last_read()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "read_receipt",
                "user_id": str(self.user.id),
                "read_at": timezone.now().isoformat(),
            },
        )

    async def handle_add_reaction(self, data):
        reaction = (data.get("reaction") or "").strip()
        message_id = data.get("message_id")
        if not reaction or not message_id:
            return

        reaction_payload = await self.save_reaction(message_id, reaction)
        if not reaction_payload:
            return

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "reaction_event",
                "reaction": reaction_payload,
            },
        )

    # ----- Broadcast Handlers -----

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))

    async def typing_indicator(self, event):
        if event["user_id"] != str(self.user.id):
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "typing",
                        "user_id": event["user_id"],
                        "username": event["username"],
                        "is_typing": event["is_typing"],
                    }
                )
            )

    async def read_receipt(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "read_receipt",
                    "user_id": event["user_id"],
                    "read_at": event["read_at"],
                }
            )
        )

    async def reaction_event(self, event):
        payload = event["reaction"]
        payload["type"] = "reaction"
        await self.send(text_data=json.dumps(payload))

    async def user_online(self, event):
        if event["user_id"] != str(self.user.id):
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "user_online",
                        "user_id": event["user_id"],
                        "username": event["username"],
                    }
                )
            )

    async def user_offline(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "user_offline",
                    "user_id": event["user_id"],
                }
            )
        )

    # ----- Database helpers -----

    @database_sync_to_async
    def get_conversation(self):
        from .models import Conversation

        return (
            Conversation.objects.filter(id=self.conversation_id)
            .values("id", "organization_id")
            .first()
        )

    @database_sync_to_async
    def is_participant(self):
        from .models import ConversationParticipant

        return ConversationParticipant.objects.filter(
            conversation_id=self.conversation_id,
            organization_id=self.organization_id,
            user_id=self.user.id,
        ).exists()

    @database_sync_to_async
    def save_message(self, content, reply_to_id=None):
        from .models import Conversation, Message

        conversation = (
            Conversation.objects.select_for_update()
            .filter(id=self.conversation_id, organization_id=self.organization_id)
            .first()
        )
        if not conversation:
            return None

        reply_to = None
        if reply_to_id:
            reply_to = (
                Message.objects.filter(
                    id=reply_to_id,
                    conversation_id=self.conversation_id,
                    organization_id=self.organization_id,
                )
                .first()
            )
            if not reply_to:
                return None

        message = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            content=content,
            reply_to=reply_to,
            organization=conversation.organization,
            created_by=self.user,
        )

        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=["last_message_at"])

        return {
            "message_id": str(message.id),
            "content": message.content,
            "created_at": message.created_at.isoformat(),
            "reply_to": str(reply_to.id) if reply_to else None,
            "reply_preview": (reply_to.content[:120] if reply_to else None),
        }

    @database_sync_to_async
    def save_reaction(self, message_id, reaction):
        from .models import Message, MessageReaction

        message = Message.objects.filter(
            id=message_id,
            conversation_id=self.conversation_id,
            organization_id=self.organization_id,
        ).first()
        if not message:
            return None

        MessageReaction.objects.update_or_create(
            message=message,
            user_id=self.user.id,
            reaction=reaction,
            defaults={"organization": message.organization},
        )

        return {
            "message_id": str(message.id),
            "reaction": reaction,
            "user_id": str(self.user.id),
            "username": self._user_display_name(),
        }

    @database_sync_to_async
    def update_last_read(self):
        from .models import ConversationParticipant

        ConversationParticipant.objects.filter(
            conversation_id=self.conversation_id,
            organization_id=self.organization_id,
            user_id=self.user.id,
        ).update(last_read_at=timezone.now())

    def _user_display_name(self):
        return (
            getattr(self.user, "full_name", None)
            or self.user.get_full_name()
            or self.user.email
        )


class MeetingConsumer(AsyncWebsocketConsumer):
    """WebRTC signaling consumer for tenant-scoped meeting rooms."""

    async def connect(self):
        self.user = self.scope.get("user")
        self.organization = self.scope.get("organization")
        self.organization_id = str(self.organization.id) if self.organization else None
        self.room_id = (
            self.scope.get("url_route", {})
            .get("kwargs", {})
            .get("room_id")
        )

        if (
            not self.user
            or self.user.is_anonymous
            or not self.room_id
            or not self.organization_id
        ):
            await self.close(code=4401)
            return

        if self.scope.get("org_mismatch"):
            await self.close(code=4403)
            return

        meeting = await self.get_meeting()
        if not meeting:
            await self.close(code=4404)
            return

        self.meeting_org_id = str(meeting["organization_id"])
        if self.meeting_org_id != self.organization_id:
            await self.close(code=4403)
            return

        self.room_group_name = f"meeting_{self.room_id}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "meeting_presence",
                "action": "join",
                "user_id": str(self.user.id),
                "username": self._user_display_name(),
            },
        )

    async def disconnect(self, close_code):
        if getattr(self, "room_group_name", None):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "meeting_presence",
                    "action": "leave",
                    "user_id": str(self.user.id),
                },
            )
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return

        event_type = payload.get("type")
        allowed_events = {"offer", "answer", "ice_candidate", "leave", "screen_share_started", "screen_share_stopped"}
        if event_type not in allowed_events:
            return

        if event_type == "leave":
            await self.disconnect(1000)
            await self.close()
            return

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "meeting_signal",
                "event": event_type,
                "sender_id": str(self.user.id),
                "username": self._user_display_name(),
                "payload": payload.get("payload"),
                "target": payload.get("target"),
            },
        )

    async def meeting_signal(self, event):
        if event["sender_id"] == str(self.user.id):
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": event["event"],
                    "sender_id": event["sender_id"],
                    "username": event["username"],
                    "payload": event.get("payload"),
                    "target": event.get("target"),
                }
            )
        )

    async def meeting_presence(self, event):
        if event.get("user_id") == str(self.user.id) and event.get("action") == "join":
            return
        await self.send(
            text_data=json.dumps(
                {
                    "type": "meeting_presence",
                    "action": event.get("action"),
                    "user_id": event.get("user_id"),
                    "username": event.get("username"),
                }
            )
        )

    @database_sync_to_async
    def get_meeting(self):
        from .models import MeetingRoom

        return (
            MeetingRoom.objects.filter(room_id=self.room_id, is_active=True)
            .values("id", "organization_id")
            .first()
        )

    def _user_display_name(self):
        return (
            getattr(self.user, "full_name", None)
            or self.user.get_full_name()
            or self.user.email
        )
