from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Puzzle(models.Model):
    CATEGORIES = [
        ('PY', 'Python'),
        ('AI', 'AI/ML'),
        ('DS', 'Data Science'),
    ]
    
    LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
    ]

    PUZZLE_TYPES = [
        ('mcq', 'Multiple Choice Question'),
        ('code', 'Coding Challenge'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=2, choices=CATEGORIES)
    level = models.CharField(
        max_length=20,
        choices=LEVEL_CHOICES,
        default='beginner'
    )
    puzzle_type = models.CharField(
        max_length=4,
        choices=PUZZLE_TYPES,
        default='mcq'  # Default to MCQ, will be overridden for intermediate/expert
    )
    points = models.IntegerField(default=10)
    test_cases = models.JSONField(default=dict)  # For MCQ: options, For Code: input-output pairs
    solution = models.TextField()  # For MCQ: correct answer letter (A,B,C,D), For Code: solution code
    expected_output = models.TextField(blank=True, null=True, help_text="Expected output for coding puzzles")
    starter_code = models.TextField(
        blank=True,
        null=True,
        help_text="Initial code template for coding puzzles"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Automatically set puzzle_type based on level
        if self.level == 'beginner':
            self.puzzle_type = 'mcq'
        else:
            self.puzzle_type = 'code'
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['level', '-created_at']

class Submission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)
    code = models.TextField(null=True, blank=True)  # Used for coding challenges
    answer = models.CharField(max_length=500, null=True, blank=True)  # Used for MCQs or code output
    is_correct = models.BooleanField(default=False)
    feedback = models.JSONField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.puzzle.title}"

    def save(self, *args, **kwargs):
        """Override save method to validate based on puzzle type."""
        if self.puzzle.puzzle_type == 'mcq':
            self.is_correct = self.answer == self.puzzle.solution
        else:  # Coding challenge
            # Simplified validation: compare answer with solution output
            # Note: You might want to implement actual code execution here
            self.is_correct = self.answer == self.puzzle.solution
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ['user', 'puzzle']
        ordering = ['-submitted_at']

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Fixed typo: on_dielete -> on_delete
    total_points = models.IntegerField(default=0)
    puzzles_solved = models.IntegerField(default=0)
    solved_puzzles = models.ManyToManyField(Puzzle, blank=True)

    def __str__(self):
        return self.user.username

    def update_profile(self):
        """Utility method to update total points and puzzles solved."""
        solved_submissions = Submission.objects.filter(user=self.user, is_correct=True)
        self.total_points = sum(submission.puzzle.points for submission in solved_submissions)
        self.puzzles_solved = solved_submissions.count()
        self.save()

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile instance when a new user is created."""
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save the UserProfile instance after a user is saved."""
    instance.userprofile.save()