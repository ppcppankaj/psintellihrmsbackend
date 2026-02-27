import factory
from apps.authentication.models import User
from apps.employees.models import Employee

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    email = factory.Sequence(lambda n: f'user{n}@example.com')
    password = 'testpass123'
    is_verified = True

class EmployeeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Employee
    user = factory.SubFactory(UserFactory)
    employee_id = factory.Sequence(lambda n: f'EMP{n:05d}')
    date_of_joining = factory.Faker('date_object')
