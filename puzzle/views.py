from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy
from .models import Puzzle, Submission, UserProfile
from .forms import PuzzleSubmissionForm, SignUpForm, EmailAuthenticationForm
import google.generativeai as genai
from decouple import config
import json
import logging
import re

# Configure logging
logger = logging.getLogger(__name__)

# Configure Gemini API globally
genai.configure(api_key=config('GEMINI_API_KEY'))
gemini_pro = genai.GenerativeModel('gemini-pro')
gemini_mini = genai.GenerativeModel('gemini-1.5-flash')

@login_required
def index(request):
    """Display all puzzles ordered by category and level with filtering."""
    category_filter = request.GET.get('category', 'all')
    level_filter = request.GET.get('level', 'all')
    
    puzzles = Puzzle.objects.all()
    
    if category_filter != 'all':
        puzzles = puzzles.filter(category=category_filter)
    
    if category_filter != 'all' and level_filter != 'all':
        puzzles = puzzles.filter(level=level_filter)
    
    for puzzle in puzzles:
        puzzle.level_display = puzzle.get_level_display()
        puzzle.category_display = puzzle.get_category_display()
        puzzle.type_display = 'MCQ' if puzzle.puzzle_type == 'mcq' else 'Coding'
    
    return render(request, 'puzzle/index.html', {
        'puzzles': puzzles,
        'current_category': category_filter,
        'current_level': level_filter,
        'categories': Puzzle.CATEGORIES,
        'level_choices': Puzzle.LEVEL_CHOICES
    })

@login_required
def puzzle_detail(request, puzzle_id):
    """Display puzzle details and redirect to solve page for submission."""
    puzzle = get_object_or_404(Puzzle, pk=puzzle_id)
    user_profile = request.user.userprofile
    existing_submission = Submission.objects.filter(user=request.user, puzzle=puzzle).first()

    context = {
        'puzzle': puzzle,
        'submission': existing_submission,
        'is_solved': puzzle in user_profile.solved_puzzles.all(),
        'type_display': 'MCQ' if puzzle.puzzle_type == 'mcq' else 'Coding',
    }
    return render(request, 'puzzle/detail.html', context)

@login_required
def solve_puzzle(request, puzzle_id):
    """Handle puzzle solving with LLM validation for coding puzzles and allow retries."""
    puzzle = get_object_or_404(Puzzle, pk=puzzle_id)
    user_profile = request.user.userprofile
    existing_submission = Submission.objects.filter(user=request.user, puzzle=puzzle).first()
    stored_code = request.session.get(f'retry_code_{puzzle_id}', '')

    if request.method == 'POST':
        form = PuzzleSubmissionForm(request.POST, puzzle=puzzle)
        if form.is_valid():
            if existing_submission:
                submission = existing_submission
            else:
                submission = form.save(commit=False)
                submission.user = request.user
                submission.puzzle = puzzle

            if puzzle.puzzle_type == 'mcq':
                submission.answer = form.cleaned_data['answer']
                submission.status = 'completed'
            else:
                submission.code = form.cleaned_data['code']
                submission.status = 'pending'

            # Rest of validation logic remains the same
            if puzzle.puzzle_type == 'mcq':
                submission.save()
                if submission.is_correct:
                    if not existing_submission or not existing_submission.is_correct:
                        user_profile.total_points += puzzle.points
                        user_profile.puzzles_solved += 1
                        user_profile.solved_puzzles.add(puzzle)
                        user_profile.save()
                    messages.success(request, f"Correct! You earned {puzzle.points} points!")
                    return redirect('puzzle:detail', puzzle_id=puzzle_id)
                else:
                    messages.error(request, "Incorrect solution.")
                    form = PuzzleSubmissionForm(puzzle=puzzle, initial={'answer': form.cleaned_data['answer']})
            else:  # Coding puzzle
                user_code = form.cleaned_data['code']
                submission.code = user_code
                submission.status = 'pending'  # Set initial status for coding puzzles

                validation_prompt = f"""
                    Validate this Python code solution against the problem description. Respond ONLY with a JSON object.
                    Problem: {puzzle.description}
                    
                    Code:
                    ```python
                    {user_code}
                    ```
                    
                    Return a JSON object with these fields:
                    - is_valid: boolean
                    - message: string (explanation)
                    - errors: array of strings (if any)
                """

                try:
                    response = gemini_mini.generate_content(validation_prompt)
                    # Add response cleaning and better error handling
                    response_text = response.text.strip()
                    # Try to extract JSON if it's wrapped in ```json or ``` blocks
                    json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', response_text, re.DOTALL)
                    if json_match:
                        response_text = json_match.group(1)
                    
                    try:
                        validation_result = json.loads(response_text)
                        logger.debug(f"Validation result: {validation_result}")
                        
                        if not isinstance(validation_result, dict):
                            raise ValueError("Validation result is not a dictionary")
                        
                        if 'is_valid' not in validation_result or 'message' not in validation_result:
                            raise ValueError("Missing required fields in validation result")
                        
                        if validation_result['is_valid']:
                            submission.is_correct = True
                            submission.status = 'completed'
                            submission.save()
                            if not existing_submission or not existing_submission.is_correct:
                                user_profile.total_points += puzzle.points
                                user_profile.puzzles_solved += 1
                                user_profile.solved_puzzles.add(puzzle)
                                user_profile.save()
                            messages.success(request, f"Correct! You earned {puzzle.points} points!")
                            return redirect('puzzle:detail', puzzle_id=puzzle_id)
                        else:
                            submission.status = 'failed'
                            submission.save()
                            error_message = validation_result.get('message', 'Invalid solution')
                            messages.error(request, f"Incorrect solution: {error_message}")
                            request.session[f'retry_code_{puzzle_id}'] = user_code
                            
                    except json.JSONDecodeError as je:
                        logger.error(f"JSON parsing error: {str(je)}\nResponse text: {response_text}")
                        messages.error(request, "Invalid response format from validation service.")
                        submission.status = 'error'
                        submission.save()
                        
                except Exception as e:
                    logger.error(f"Validation error: {str(e)}\nFull traceback:", exc_info=True)
                    messages.error(request, "An error occurred during validation. Please try again.")
                    submission.status = 'error'
                    submission.save()

    else:
        initial_data = {'code': stored_code} if stored_code else None
        form = PuzzleSubmissionForm(puzzle=puzzle, initial=initial_data)

    return render(request, 'puzzle/solve.html', {
        'form': form,
        'puzzle': puzzle,
        'submission': existing_submission
    })

@login_required
def submit_solution(request, puzzle_id):
    """Handle puzzle solution submission (alternative entry point)."""
    return puzzle_detail(request, puzzle_id)  # Reuse puzzle_detail view logic

def leaderboard(request):
    """Display the top 10 users by points."""
    top_users = UserProfile.objects.all().order_by('-total_points')[:10]
    return render(request, 'puzzle/leaderboard.html', {'top_users': top_users})

class CustomLoginView(LoginView):
    """Custom login view using email authentication."""
    form_class = EmailAuthenticationForm
    template_name = 'registration/login.html'
    redirect_authenticated_user = True
    success_url = reverse_lazy('puzzle:index')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Welcome back, {self.request.user.username}!')
        return response

def signup(request):
    """Handle user signup with custom form."""
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome, {user.username}! Your account has been created.")
            return redirect('puzzle:index')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})

@login_required
def profile(request):
    user_profile = request.user.userprofile
    submissions = Submission.objects.filter(user=request.user).order_by('-submitted_at')
    context = {
        'user_profile': user_profile,
        'submissions': submissions,
        'total_points': user_profile.total_points,
        'puzzles_solved': user_profile.puzzles_solved,
    }
    return render(request, 'puzzle/profile.html', context)

def logout_view(request):
    """Handle user logout."""
    if request.method == 'POST':
        logout(request)
        messages.info(request, "You have been logged out successfully.")
    return redirect('puzzle:index')
