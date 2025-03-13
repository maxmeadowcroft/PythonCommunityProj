from django.contrib import admin
from django.urls import path
from django.shortcuts import render, reverse
from django.utils.html import format_html
from django.contrib.admin import AdminSite
from django.core.paginator import Paginator
from django.db.models import Count
from django.utils import timezone
import logging
import json
import re
from datetime import timedelta
from decouple import config
import google.generativeai as genai
from .models import UserProfile, Puzzle, Submission

logger = logging.getLogger(__name__)

class CustomAdminSite(AdminSite):
    site_header = "PuzzleHub Admin"
    site_title = "PuzzleHub Admin Portal"
    index_title = "Welcome to PuzzleHub Admin Portal"
    site_url = "/"

    def get_urls(self):
        default_urls = super().get_urls()
        custom_urls = [
            path('custom-dashboard/', self.admin_view(self.custom_dashboard_view), name='custom-dashboard'),
            path('manage-users/', self.admin_view(self.manage_users_view), name='manage-users'),
            path('manage-puzzles/', self.admin_view(self.manage_puzzles_view), name='manage-puzzles'),
            path('manage-submissions/', self.admin_view(self.manage_submissions_view), name='manage-submissions'),
            path('generate-puzzles/', self.admin_view(self.generate_puzzle_view), name='generate-puzzles'),
            path('edit-puzzle/<int:puzzle_id>/', self.admin_view(self.edit_puzzle_view), name='edit-puzzle'),
            path('delete-puzzle/<int:puzzle_id>/', self.admin_view(self.delete_puzzle_view), name='delete-puzzle'),
        ]
        return custom_urls + default_urls

    def custom_dashboard_view(self, request):
        try:
            context = self.each_context(request)
            submissions_list = Submission.objects.select_related('user', 'puzzle').order_by('-submitted_at')
            paginator = Paginator(submissions_list, 10)
            page_num = request.GET.get('page', 1)
            submissions_page = paginator.get_page(page_num)

            total_users = UserProfile.objects.count()
            total_puzzles = Puzzle.objects.count()
            total_submissions = Submission.objects.count()
            thirty_days_ago = timezone.now() - timedelta(days=30)

            top_users = UserProfile.objects.filter(
                user__submission__submitted_at__gte=thirty_days_ago
            ).annotate(
                solved_count=Count('user__submission', filter=Submission.objects.filter(is_correct=True))
            ).order_by('-solved_count')[:5]

            context.update({
                'title': "Puzzle Management Dashboard",
                'user_profiles': UserProfile.objects.all(),
                'puzzles': Puzzle.objects.all(),
                'submissions': submissions_page,
                'beginner_puzzles': Puzzle.objects.filter(level='beginner', puzzle_type='mcq'),
                'intermediate_puzzles': Puzzle.objects.filter(level='intermediate', puzzle_type='code'),
                'expert_puzzles': Puzzle.objects.filter(level='expert', puzzle_type='code'),
                'total_users': total_users,
                'total_puzzles': total_puzzles,
                'total_submissions': total_submissions,
                'top_users': top_users,
                'page_obj': submissions_page,
                'available_apps': self.get_app_list(request),
                'is_popup': False,
            })
            return render(request, 'admin/custom_dashboard.html', context)
        except Exception as e:
            logger.error(f"Dashboard view error: {str(e)}")
            context.update({'error': str(e)})
            return render(request, 'admin/custom_dashboard.html', context)

    def manage_users_view(self, request):
        try:
            context = self.each_context(request)
            profiles = UserProfile.objects.select_related('user').all()
            paginator = Paginator(profiles, 10)
            page_num = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_num)

            context.update({
                'title': "Manage Users",
                'user_profiles': page_obj,
                'page_obj': page_obj,
            })
            return render(request, 'admin/manage_users.html', context)
        except Exception as e:
            logger.error(f"Users view error: {str(e)}")
            context.update({'error': str(e)})
            return render(request, 'admin/manage_users.html', context)

    def manage_puzzles_view(self, request):
        try:
            context = self.each_context(request)
            category = request.GET.get('category', 'all')
            level = request.GET.get('level', None)

            puzzles = Puzzle.objects.all()
            if category != 'all':
                puzzles = puzzles.filter(category=category)
                if level:
                    puzzles = puzzles.filter(level=level)

            paginator = Paginator(puzzles, 10)
            page_num = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_num)

            context.update({
                'title': "Manage Puzzles",
                'puzzles': page_obj,
                'active_category': category,
                'active_level': level,
                'page_obj': page_obj,
            })
            return render(request, 'admin/manage_puzzles.html', context)
        except Exception as e:
            logger.error(f"Puzzles view error: {str(e)}")
            context.update({'error': str(e)})
            return render(request, 'admin/manage_puzzles.html', context)

    def manage_submissions_view(self, request):
        try:
            context = self.each_context(request)
            submissions = Submission.objects.select_related('user', 'puzzle').order_by('-submitted_at')
            paginator = Paginator(submissions, 10)
            page_num = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_num)

            context.update({
                'title': "Manage Submissions",
                'submissions': page_obj,
                'page_obj': page_obj,
            })
            return render(request, 'admin/manage_submissions.html', context)
        except Exception as e:
            logger.error(f"Submissions view error: {str(e)}")
            context.update({'error': str(e)})
            return render(request, 'admin/manage_submissions.html', context)

    def generate_puzzle_view(self, request):
        try:
            context = self.each_context(request)
            context.update({'title': "Generate Puzzles"})

            if request.method == 'POST':
                num_puzzles = int(request.POST.get('num_puzzles', 15))
                category = request.POST.get('category', 'PY')
                level = request.POST.get('level', 'beginner')
                cat_name = dict(Puzzle.CATEGORIES).get(category, 'Python')

                # Configure Gemini
                genai.configure(api_key=config('GEMINI_API_KEY'))
                model = genai.GenerativeModel('gemini-pro')
                puzzles_created = 0
                valid_puzzles = []
                
                # Get existing titles for duplicate check
                existing_titles = set(Puzzle.objects.values_list('title', flat=True))

                if level == 'beginner':
                    prompt = f"""Return JSON only. Generate {num_puzzles} unique MCQs for {cat_name}.
                    Each question MUST have a detailed description.
                    Format: [{{"title": "short question", "description": "detailed explanation of the question", 
                    "options": {{"A": "option1", "B": "option2", "C": "option3", "D": "option4"}}, 
                    "correct_answer": "A/B/C/D"}}]"""
                else:
                    prompt = f"""Return JSON only. Generate {num_puzzles} unique {level} {cat_name} coding puzzles.
                    Each puzzle MUST have a detailed description.
                    Format: [{{"title": "short name", "description": "detailed problem statement with requirements", 
                    "test_cases": {{"test1": {{"input": "example", "output": "result"}}, 
                    "test2": {{"input": "example2", "output": "result2"}}}}}}]"""

                max_retries = 3
                for retry in range(max_retries):
                    try:
                        response = model.generate_content(prompt)
                        raw_response = response.text.strip()
                        
                        # Simple JSON cleanup
                        cleaned_response = raw_response.replace('```json', '').replace('```', '')
                        puzzles_data = json.loads(cleaned_response)

                        if not isinstance(puzzles_data, list):
                            puzzles_data = [puzzles_data]

                        for puzzle_data in puzzles_data:
                            if puzzles_created >= num_puzzles:
                                break

                            # Validate required fields
                            if not all(k in puzzle_data for k in ['title', 'description']):
                                continue
                            
                            title = puzzle_data['title'].strip()
                            description = puzzle_data['description'].strip()
                            
                            # Skip if title exists or description is empty
                            if title in existing_titles or not description:
                                continue

                            test_cases = (puzzle_data.get('options', {}) if level == 'beginner' 
                                        else puzzle_data.get('test_cases', {}))
                            
                            # Create puzzle with default description if needed
                            Puzzle.objects.create(
                                title=title,
                                description=description or f"Practice question about {cat_name}",
                                category=category,
                                level=level,
                                puzzle_type='mcq' if level == 'beginner' else 'code',
                                points=10 if level == 'beginner' else (20 if level == 'intermediate' else 30),
                                test_cases=test_cases,
                                solution=puzzle_data.get('correct_answer', '') if level == 'beginner' else ''
                            )
                            
                            puzzles_created += 1
                            existing_titles.add(title)
                            valid_puzzles.append(title)

                        if puzzles_created >= num_puzzles:
                            break

                    except json.JSONDecodeError as e:
                        if retry == max_retries - 1:
                            logger.error(f"JSON parsing failed after {max_retries} attempts: {str(e)}")
                            context.update({'error': f"Failed to generate valid puzzles after {max_retries} attempts"})
                            return render(request, 'admin/generate_puzzles.html', context)
                        continue

                if puzzles_created == 0:
                    context.update({'error': "No valid puzzles could be created"})
                else:
                    context.update({
                        'success': f"Successfully created {puzzles_created} puzzles"
                    })
                return render(request, 'admin/generate_puzzles.html', context)

            return render(request, 'admin/generate_puzzles.html', context)

        except Exception as e:
            logger.error(f"Puzzle generation error: {str(e)}")
            context.update({'error': str(e)})
            return render(request, 'admin/generate_puzzles.html', context)

    def edit_puzzle_view(self, request, puzzle_id):
        try:
            puzzle = Puzzle.objects.get(id=puzzle_id)
            context = self.each_context(request)
            context.update({
                'title': f"Edit Puzzle: {puzzle.title}",
                'puzzle': puzzle,
            })

            if request.method == 'POST':
                action = request.POST.get('action')
                
                if action == 'update_with_llm':
                    genai.configure(api_key=config('GEMINI_API_KEY'))
                    model = genai.GenerativeModel('gemini-pro')
                    
                    if puzzle.level == 'beginner':
                        prompt = f"""
                        Return only valid JSON, no additional text:
                        Update this beginner-level MCQ about {dict(Puzzle.CATEGORIES)[puzzle.category]}:
                        - Current title: "{puzzle.title}"
                        - Current description: "{puzzle.description}"
                        - Current options: {json.dumps(puzzle.test_cases)}
                        - Current correct answer: "{puzzle.solution}"
                        Provide an improved version with:
                        - A clear question (title)
                        - A brief description
                        - 4 options (A, B, C, D) as a JSON dictionary
                        - The correct answer (A, B, C, or D)
                        Return as a single JSON object.
                        """
                    else:
                        prompt = f"""
                        Return only valid JSON, no additional text:
                        Update this {puzzle.level}-level {dict(Puzzle.CATEGORIES)[puzzle.category]} coding puzzle:
                        - Current title: "{puzzle.title}"
                        - Current description: "{puzzle.description}"
                        - Current test cases: {json.dumps(puzzle.test_cases)}
                        Provide an improved version with:
                        - A title
                        - A detailed problem description
                        - Test cases as a JSON dictionary with input-output pairs ({'3' if puzzle.level == 'intermediate' else '5'} minimum)
                        Return as a single JSON object.
                        """

                    response = model.generate_content(prompt)
                    logger.info(f"Raw LLM update response for puzzle {puzzle.id}: {response.text}")

                    if not response.text or response.text.strip() == "":
                        logger.error(f"Empty LLM update response for puzzle {puzzle.id}")
                        context.update({'error': "Empty LLM update response"})
                        return render(request, 'admin/edit_puzzle.html', context)

                    try:
                        updated_data = json.loads(response.text)
                        puzzle.title = updated_data['title']
                        puzzle.description = updated_data['description']
                        puzzle.test_cases = updated_data.get('options', updated_data.get('test_cases', {}))
                        if puzzle.level == 'beginner':
                            puzzle.solution = updated_data.get('correct_answer', '')
                        puzzle.save()
                        context.update({'success': "Puzzle updated successfully with LLM!"})
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse LLM update response for puzzle {puzzle.id}: {str(e)} - Raw: {response.text}")
                        context.update({'error': f"Failed to parse LLM update response: {str(e)}"})
                        return render(request, 'admin/edit_puzzle.html', context)

                else:  # Manual update
                    puzzle.title = request.POST.get('title', puzzle.title)
                    puzzle.description = request.POST.get('description', puzzle.description)
                    puzzle.category = request.POST.get('category', puzzle.category)
                    puzzle.level = request.POST.get('level', puzzle.level)
                    puzzle.puzzle_type = 'mcq' if puzzle.level == 'beginner' else 'code'
                    puzzle.points = int(request.POST.get('points', puzzle.points))

                    if puzzle.puzzle_type == 'mcq':
                        test_cases = {
                            'A': request.POST.get('option_a', ''),
                            'B': request.POST.get('option_b', ''),
                            'C': request.POST.get('option_c', ''),
                            'D': request.POST.get('option_d', ''),
                        }
                        if not all(test_cases.values()):
                            context.update({'error': "All MCQ options must be filled"})
                            return render(request, 'admin/edit_puzzle.html', context)
                        puzzle.test_cases = test_cases
                        puzzle.solution = request.POST.get('solution', puzzle.solution)
                        if puzzle.solution not in ['A', 'B', 'C', 'D']:
                            context.update({'error': "Correct answer must be A, B, C, or D for MCQ"})
                            return render(request, 'admin/edit_puzzle.html', context)
                    else:
                        try:
                            puzzle.test_cases = json.loads(request.POST.get('test_cases', json.dumps(puzzle.test_cases)))
                        except json.JSONDecodeError:
                            context.update({'error': "Invalid JSON format in test cases"})
                            return render(request, 'admin/edit_puzzle.html', context)
                        puzzle.solution = ''  # No solution for coding puzzles

                    puzzle.save()
                    context.update({'success': "Puzzle updated successfully!"})

                return render(request, 'admin/edit_puzzle.html', context)

            return render(request, 'admin/edit_puzzle.html', context)
        except Puzzle.DoesNotExist:
            context = self.each_context(request)
            context.update({'error': "Puzzle not found"})
            return render(request, 'admin/edit_puzzle.html', context)
        except Exception as e:
            logger.error(f"Edit puzzle error: {str(e)}")
            context.update({'error': str(e)})
            return render(request, 'admin/edit_puzzle.html', context)

    def delete_puzzle_view(self, request, puzzle_id):
        try:
            puzzle = Puzzle.objects.get(id=puzzle_id)
            context = self.each_context(request)
            context.update({
                'title': f"Delete Puzzle: {puzzle.title}",
                'puzzle': puzzle,
            })

            if request.method == 'POST':
                if request.POST.get('confirm') == 'yes':
                    puzzle_title = puzzle.title
                    puzzle.delete()
                    context.update({'success': f"Puzzle '{puzzle_title}' deleted successfully!"})
                    return render(request, 'admin/delete_puzzle.html', context, {'redirect': reverse('custom_admin:manage-puzzles')})
                else:
                    context.update({'error': "Deletion cancelled."})

            return render(request, 'admin/delete_puzzle.html', context)
        except Puzzle.DoesNotExist:
            context = self.each_context(request)
            context.update({'error': "Puzzle not found"})
            return render(request, 'admin/delete_puzzle.html', context)
        except Exception as e:
            logger.error(f"Delete puzzle error: {str(e)}")
            context.update({'error': str(e)})
            return render(request, 'admin/delete_puzzle.html', context)

class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_points', 'puzzles_solved', 'rank_display')
    search_fields = ('user__username', 'user__email')
    list_filter = ('total_points', 'puzzles_solved')
    readonly_fields = ('total_points', 'puzzles_solved')

    def rank_display(self, obj):
        return format_html(
            '<span style="color: {}">{}</span>',
            '#FFD700' if obj.total_points > 1000 else '#C0C0C0',
            f'Rank {obj.get_rank()}'
        )
    rank_display.short_description = 'Rank'

class PuzzleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'level', 'puzzle_type', 'points', 'created_at')
    list_filter = ('category', 'level', 'puzzle_type', 'created_at')
    search_fields = ('title', 'description')
    date_hierarchy = 'created_at'

class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'puzzle', 'is_correct', 'submitted_at')
    list_filter = ('is_correct', 'submitted_at')
    search_fields = ('user__username', 'puzzle__title')
    date_hierarchy = 'submitted_at'

custom_admin_site = CustomAdminSite(name='custom_admin')
custom_admin_site.register(UserProfile, UserProfileAdmin)
custom_admin_site.register(Puzzle, PuzzleAdmin)
custom_admin_site.register(Submission, SubmissionAdmin)

admin.site.register(Puzzle)