from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, firebase_uid, **extra_fields):
        user = self.model(firebase_uid=firebase_uid, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    firebase_uid = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=150)
    # Contact details are metadata; identities are linked only by verified Firebase UID.
    email = models.EmailField(blank=True)
    email_verified = models.BooleanField(default=False)
    phone_number = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "firebase_uid"
    objects = UserManager()


class UserPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="preferences")
    profession = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("student", "Student"),
            ("professional", "Working Professional"),
            ("entrepreneur", "Entrepreneur"),
            ("personal", "Personal"),
        ],
    )
    focus_areas = models.JSONField(default=list)
    onboarding_completed = models.BooleanField(default=False)
