"""
Recruitment Services - Resume parsing and Candidate management
"""

import json
from .models import Candidate, JobApplication, JobPosting

class RecruitmentService:
    """
    Logic for recruitment workflows and AI integration stubs.
    """

    @staticmethod
    def parse_resume(candidate_id):
        """
        Mock AI Resume parsing logic.
        In production, this would call an LLM or OCR service.
        """
        candidate = Candidate.objects.get(id=candidate_id)
        
        # Mocking parsed data
        mock_data = {
            "skills": ["Python", "Django", "React", "PostgreSQL"],
            "total_experience": 5.5,
            "education": [{"degree": "B.Tech", "institution": "IIT"}]
        }
        
        candidate.parsed_data = mock_data
        candidate.skills = mock_data["skills"]
        candidate.total_experience = mock_data["total_experience"]
        candidate.save()
        
        return mock_data

    @staticmethod
    def score_application(application_id):
        """
        Score a job application based on resume vs job requirements.
        """
        application = JobApplication.objects.get(id=application_id)
        job = application.job
        candidate = application.candidate
        
        # Simple mock scoring logic
        score = 85.5  # Fixed mock score
        
        application.ai_score = score
        application.ai_insights = {
            "matching_skills": ["Python", "Django"],
            "missing_skills": ["Redis"],
            "recommendation": "Strong match"
        }
        application.save()
        
        return score
