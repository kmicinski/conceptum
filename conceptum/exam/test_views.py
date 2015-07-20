from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.db import models, transaction
from django.test import SimpleTestCase
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

import reversion

from profiles.tests import set_up_user
from interviews.models import get_concept_list, DummyConcept as Concept
from .models import Exam, FreeResponseQuestion, MultipleChoiceQuestion, MultipleChoiceOption,\
                    ExamKind, ExamStage, Question, ResponseSet, ExamResponse

def create_exam():
    """
    gets or creates an exam and some questions
    """
    exam = Exam.objects.create(name='Test Exam',
                               kind = ExamKind.CI,
                               stage = ExamStage.DEV,
                               description='an exam for testing')
    concept_type = ContentType.objects.get_for_model(Concept)
    concept = Concept.objects.get(name = "Concept A")
    FreeResponseQuestion.objects.create(exam=exam,
                                question="What is the answer to this FR question?",
                                content_type=concept_type,
                                object_id=concept.id)
    concept = Concept.objects.get(name = "Concept B")
    mcq = MultipleChoiceQuestion.objects.create(exam=exam,
                                question="What is the answer to this MC question?",
                                content_type=concept_type,
                                object_id=concept.id)
    MultipleChoiceOption.objects.create(question=mcq, text="choice 1", index=1, is_correct=True)
    MultipleChoiceOption.objects.create(question=mcq, text="choice 2", index=2)
    MultipleChoiceOption.objects.create(question=mcq, text="choice 3", index=3)
    return exam

class DevViewsTest(SimpleTestCase):
    def setUp(self):
        get_concept_list()
        self.user = set_up_user()
    
    def test_index_view(self):
        # User not logged in, redirected
        response = self.client.get(reverse('CI_exam:index'))
        self.assertRedirects(response, '/accounts/login/?next=/exams/CI/dev/')
        
        # User logged in, not contrib
        self.client.login(email=self.user.email, password='password')
        response = self.client.get(reverse('exam:index'))
        self.assertEqual(response.status_code, 403)        
        
        # Contrib user logs in, no exams in database
        self.user.profile.is_contrib = True
        self.user.profile.save()
        for exam in Exam.objects.all():
            exam.delete()
        self.client.login(email=self.user.email, password='password')
        response = self.client.get(reverse('exam:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response,"no CIs available")
        
        # Test Exam should now be listed
        exam = create_exam()
        response = self.client.get(reverse('exam:index'))
        self.assertContains(response,exam.name)
        
    def test_detail_view(self):
        exam = create_exam()
        
        # User not logged in, redirected
        response = self.client.get(reverse('CI_exam:detail', args=[exam.id]))
        self.assertRedirects(response, '/accounts/login/?next=/exams/CI/dev/%s/'%exam.id)
        
        # User logged in, not contrib
        self.client.login(email=self.user.email, password='password')
        response = self.client.get(reverse('exam:detail', args=[exam.id]))
        self.assertEqual(response.status_code, 403)
        
        # User is contrib
        self.user.profile.is_contrib = True
        self.user.profile.save()
        response = self.client.get(reverse('exam:detail', args=[exam.id]))
        self.assertEqual(response.status_code, 200)
        
        # exam id does not exist
        response = self.client.get(reverse('exam:detail', args=[99]))
        self.assertEqual(response.status_code, 404)
        
        # make sure questions are displayed
        response = self.client.get(reverse('exam:detail', args=[exam.id]))
        self.assertEqual(response.status_code, 200)
        for concept in (Concept.objects.all()):
            self.assertContains(response, concept)
        for question in (exam.freeresponsequestion_set.all()):
            self.assertContains(response, question.question)
        for question in (exam.multiplechoicequestion_set.all()):
            self.assertContains(response, question.question)

    def test_create_view(self):
        # User not logged in, redirected
        response = self.client.get(reverse('CI_exam:create'))
        self.assertRedirects(response, '/accounts/login/?next=/exams/CI/dev/create/')
        
        # User logged in, and contrib
        self.user.profile.is_contrib = True
        self.user.profile.save()
        self.client.login(email=self.user.email, password='password')
        response = self.client.get(reverse('exam:create'))
        self.assertEqual(response.status_code, 403)
        
        # User is staff
        self.user.is_staff = True
        self.user.save()
        response = self.client.get(reverse('exam:create'))
        self.assertEqual(response.status_code, 200)
        
        # Try to create a test
        response = self.client.post(reverse('exam:create'),
                                    {'name':'Test Create Exam','description':'xxxxxxxx'})
        self.assertRedirects(response, reverse('exam:index'))
        self.assertTrue(Exam.objects.filter(name='Test Create Exam'))

    def test_select_view(self):
        exam = create_exam()
        
        # User not logged in, redirected
        response = self.client.get(reverse('CI_exam:select_concept', args=[exam.id]))
        self.assertRedirects(response, '/accounts/login/?next=/exams/CI/dev/%s/select/'%exam.id)
        
        # User logged in, not contrib
        self.client.login(email=self.user.email, password='password')
        response = self.client.get(reverse('exam:select_concept', args=[exam.id]))
        self.assertEqual(response.status_code, 403)
        
        # User is contrib
        self.user.profile.is_contrib = True
        self.user.profile.save()
        response = self.client.get(reverse('exam:select_concept', args=[exam.id]))
        self.assertEqual(response.status_code, 200)
        
        # exam id does not exist
        response = self.client.get(reverse('exam:select_concept', args=[99]))
        self.assertEqual(response.status_code, 404)
    
        # make sure concept choices are present
        response = self.client.get(reverse('exam:select_concept', args=[exam.id]))
        self.assertEqual(response.status_code, 200)
        for concept in (Concept.objects.all()):
            self.assertContains(response, concept)
        
        # Select no concept, should get an error
        response = self.client.post(reverse('exam:select_concept', args=[exam.id]),
                                    {'concept':'',})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
            
        # Select a concept. No object is created, but we should redirect to a
        # page to create a question for this concept
        concept = Concept.objects.get(name = "Concept A")
        response = self.client.post(reverse('exam:select_concept', args=[exam.id]),
                                    {'concept':concept,})
        self.assertRedirects(response, reverse('exam:question_create',
            kwargs ={'exam_id':exam.id,'concept_id':concept.id,'question_type':'fr'}))
        
    def test_question_create_view(self):
        """        
        possible tests to add:
            Check interview and excerpt data
        """
        exam = create_exam()
        concept = Concept.objects.get(name = "Concept A")
        
        # User not logged in, redirected
        response = self.client.get(reverse('CI_exam:question_create',
            kwargs ={'exam_id':exam.id,'concept_id':concept.id,'question_type':'fr'}))
        self.assertRedirects(response,
                             '/accounts/login/?next=/exams/CI/dev/%s/%s/fr/'%(exam.id,concept.id))
        
        # User logged in, not contrib
        self.client.login(email=self.user.email, password='password')
        response = self.client.get(reverse('exam:question_create',
            kwargs ={'exam_id':exam.id,'concept_id':concept.id,'question_type':'fr'}))
        self.assertEqual(response.status_code, 403)
        
        # User is contrib
        self.user.profile.is_contrib = True
        self.user.profile.save()
        response = self.client.get(reverse('exam:question_create',
            kwargs ={'exam_id':exam.id,'concept_id':concept.id,'question_type':'fr'}))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('exam:question_create',
            kwargs ={'exam_id':exam.id,'concept_id':concept.id,'question_type':'mc'}))
        self.assertEqual(response.status_code, 200)
        
        # exam_id does not exist
        response = self.client.get(reverse('exam:question_create',
            kwargs ={'exam_id':99,'concept_id':concept.id,'question_type':'fr'}))
        self.assertEqual(response.status_code, 404)
        
        # concept_id does not exist
        response = self.client.get(reverse('exam:question_create',
            kwargs ={'exam_id':exam.id,'concept_id':99,'question_type':'fr'}))
        self.assertEqual(response.status_code, 404)
        
        # question type not 'fr' or 'mc'
        response = self.client.get(reverse('exam:question_create',
            kwargs ={'exam_id':exam.id,'concept_id':concept.id,'question_type':'xx'}))
        self.assertEqual(response.status_code, 404)
        
        # Check that submit redirects us
        response = self.client.post(reverse('exam:question_create',
            kwargs ={'exam_id':exam.id,'concept_id':concept.id,'question_type':'mc'}),
            {'question':'question', 'choice_1':'yes', 'choice_2':'no', 'correct':'1'})
        self.assertRedirects(response, reverse('exam:detail', kwargs ={'exam_id':exam.id,}))

    def test_multiple_choice_edit_view(self):
        """
        There isn't any important functionality in FreeResponseEditView that isn't also used by
        MultipleChoiceEditView, since they both subclass QuestionEditView.
        """
        exam = create_exam()
        question = MultipleChoiceQuestion.objects.get(exam=exam)
        
        # User not logged in, redirected
        response = self.client.get(reverse('CI_exam:mc_edit',kwargs ={'question_id':question.id}))
        self.assertRedirects(response,
                             '/accounts/login/?next=/exams/CI/dev/mc/%s/edit/'%question.id)
        
        # User logged in, not contrib
        self.client.login(email=self.user.email, password='password')
        response = self.client.get(reverse('CI_exam:mc_edit',kwargs ={'question_id':question.id}))
        self.assertEqual(response.status_code, 403)
        
        # User is contrib
        self.user.profile.is_contrib = True
        self.user.profile.save()
        response = self.client.get(reverse('CI_exam:mc_edit',kwargs ={'question_id':question.id}))
        self.assertEqual(response.status_code, 200)
        
        # question_id does not exist
        response = self.client.get(reverse('CI_exam:mc_edit',kwargs ={'question_id':99}))
        self.assertEqual(response.status_code, 404)
        
        # Check that the list of 3-tuples, 'choice_fields', is correctly constructed
        # with a single option
        options = question.multiplechoiceoption_set.all()
        response = self.client.get(reverse('CI_exam:mc_edit',kwargs ={'question_id':question.id}))
        choice_1_tuple = response.context['choice_fields'][0]
        self.assertIn("choice_%d"%options[0].id,choice_1_tuple[0].label_tag())
        self.assertEqual("choice 1",choice_1_tuple[1].choice_label)
        self.assertIn("index_%d"%options[0].id,choice_1_tuple[2].label_tag())
        
        # Check for all options. Should be in order. Check initial data
        i=0
        for option in options:
            choice_tuple = response.context['choice_fields'][i]
            self.assertIn(option.text,str(choice_tuple[0]))
            self.assertEqual(str(option.id),choice_tuple[1].choice_value)
            self.assertIn(str(option.index),str(choice_tuple[2]))
            i+=1
        
        # Check for new choice
        choice_tuple = response.context['choice_fields'][i]
        self.assertIn("choice_new",str(choice_tuple[0]))
        self.assertEqual('-1',choice_tuple[1].choice_value)
        self.assertTrue(choice_tuple[2])
        
        # Check that submit redirects us
        response = self.client.post(reverse('CI_exam:mc_edit',kwargs ={'question_id':question.id}),
            {'question':'question', 'choice_%d'%options[0].id:'yes', 'index_%d'%options[0].id:'1',
             'choice_%d'%options[1].id:'no', 'index_%d'%options[1].id:'2', 'correct':options[0].id,
             'concept':question.object_id})
        self.assertRedirects(response, reverse('exam:detail', kwargs ={'exam_id':exam.id,}))
    
    def test_multiple_choice_version_view(self):
        """
        There isn't any important functionality in FreeResponseVersionView that isn't also used by
        MultipleChoiceEditView, since they both subclass QuestionEditView.
        """
        exam = create_exam() # get a fresh exam
        concept_type = ContentType.objects.get_for_model(Concept)
        concept = Concept.objects.get(name = "Concept A")
        # Have to create a new question with never-before-used pk because there are version
        # objects still lingering in the database from old deleted questions.
        with transaction.atomic(), reversion.create_revision():
            question = MultipleChoiceQuestion.objects.create(
                id = 7293,
                exam=exam,
                question="A MC question for versioning?",
                number=1,
                content_type=concept_type,
                object_id=concept.id)
            MultipleChoiceOption.objects.create(id=1023, question=question, text="choice 1",
                                                index=1, is_correct=True)
            MultipleChoiceOption.objects.create(id=5839, question=question, text="choice 2",
                                                index=2)
        
        # User not logged in, redirected
        response = self.client.get(reverse('CI_exam:mc_versions',kwargs ={'question_id':question.id}))
        self.assertRedirects(response,
                             '/accounts/login/?next=/exams/CI/dev/mc/%s/versions/'%question.id)
        
        # User logged in, not contrib
        self.client.login(email=self.user.email, password='password')
        response = self.client.get(reverse('CI_exam:mc_versions',kwargs ={'question_id':question.id}))
        self.assertEqual(response.status_code, 403)
        
        # User is contrib
        self.user.profile.is_contrib = True
        self.user.profile.save()
        response = self.client.get(reverse('CI_exam:mc_versions',kwargs ={'question_id':question.id}))
        self.assertEqual(response.status_code, 200)
        
        # question_id does not exist
        response = self.client.get(reverse('CI_exam:mc_versions',kwargs ={'question_id':99}))
        self.assertEqual(response.status_code, 404)
        
        # check that there is one version
        response = self.client.get(reverse('CI_exam:mc_versions',kwargs ={'question_id':question.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, question.question, count=1)
        for option in question.multiplechoiceoption_set.all():
            self.assertContains(response, option, count=1)
        
        # update question, check that all data for both versions are listed
        old_question = question.question
        old_options = {}
        with transaction.atomic(), reversion.create_revision():
            question.question = 'this is updated question text'
            question.save()
            for option in question.multiplechoiceoption_set.all():
                old_options[option]=option.text
                option.text = option.text.upper()
                option.save()
        response = self.client.get(reverse('CI_exam:mc_versions',kwargs ={'question_id':question.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, question.question, count=1)
        self.assertContains(response, old_question, count=1)
        for option in question.multiplechoiceoption_set.all():
            self.assertContains(response, option, count=1)
            self.assertContains(response, old_options[option], count=1)
            
        # is there a way to check that these things come in the right order?
        
        # check that submit redirects us
        response = self.client.post(reverse('CI_exam:mc_versions',
                                            kwargs ={'question_id':question.id}),
                                    {'version':1})
        self.assertRedirects(response, reverse('exam:detail', kwargs ={'exam_id':exam.id,}))


class FinalizeViewTest(SimpleTestCase):
    def setUp(self):
        get_concept_list()
        self.user = set_up_user()
        
    def test_permissions(self):
        exam = create_exam()
        finalize_url = reverse('CI_exam:finalize', kwargs={'exam_id':exam.id})
        
        # User not logged in, redirected
        response = self.client.get(finalize_url)
        self.assertRedirects(response,
                             '/accounts/login/?next=/exams/CI/finalize/%s/'%exam.id)
        
        # User logged in, not staff
        self.client.login(email=self.user.email, password='password')
        response = self.client.get(finalize_url)
        self.assertEqual(response.status_code, 403)
        
        # User is staff
        self.user.is_staff = True
        self.user.save()
        response = self.client.get(finalize_url)
        self.assertEqual(response.status_code, 200)
        
        # exam_id does not exist
        response = self.client.get(reverse('CI_exam:finalize',kwargs ={'exam_id':99}))
    
    def test_with_ordered_questions(self):
        exam = create_exam()
        concept_type = ContentType.objects.get_for_model(Concept)
        concept = Concept.objects.get(name = "Concept A")
        FreeResponseQuestion.objects.create(
            exam=exam,
            question="Another free response question?",
            content_type=concept_type,
            object_id=concept.id)
        questions = exam.question_set.all()
        finalize_url = reverse('CI_exam:finalize', kwargs={'exam_id':exam.id})
        self.user.is_staff = True
        self.user.save()
        self.client.login(email=self.user.email, password='password')
        
        # check that all questions appear
        response = self.client.get(finalize_url)
        for question in exam.question_set.all():
            self.assertContains(response, question)
        self.assertEqual(len(response.context['form']['select_questions']), 3)
        
        # Step 0 - select
        response = self.client.post(finalize_url,
                                    {'finalize_view-current_step':'0',
                                     '0-select_questions':[questions[0].id,questions[1].id]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Step 2')
        self.assertEqual(len(response.context['form'].queryset),2)
        
        # Step 1 - order
        deleted_pk = questions[2].pk
        response = self.client.post(finalize_url, {'finalize_view-current_step':'1',
                                                   '1-question_%d' % questions[0].id:1,
                                                   '1-question_%d' % questions[1].id:2})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Step 3')
        
        # Step 2 - submit
        response = self.client.post(finalize_url, {'finalize_view-current_step':'2'})
        self.assertEqual(response.status_code, 302)
        exam = Exam.objects.get(pk=exam.id)
        self.assertEqual(exam.stage, ExamStage.DIST)
        self.assertFalse(exam.randomize)
        self.assertEqual(len(exam.question_set.all()), 2)
        self.assertFalse(Question.objects.filter(pk=deleted_pk))
        self.assertEqual(questions[0].number, 1)
        self.assertEqual(questions[1].number, 2)

    def test_with_randomize(self):
        exam = create_exam()
        concept_type = ContentType.objects.get_for_model(Concept)
        concept = Concept.objects.get(name = "Concept A")
        FreeResponseQuestion.objects.create(
            exam=exam,
            question="Another free response question?",
            content_type=concept_type,
            object_id=concept.id)
        questions = exam.question_set.all()
        finalize_url = reverse('CI_exam:finalize', kwargs={'exam_id':exam.id})
        self.user.is_staff = True
        self.user.save()
        self.client.login(email=self.user.email, password='password')
        
        # Step 0 - select
        response = self.client.post(finalize_url,
                                    {'finalize_view-current_step':'0',
                                     '0-select_questions':[questions[0].id,questions[1].id]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Step 2')
        self.assertEqual(len(response.context['form'].queryset),2)
        
        # Step 1 - order
        deleted_pk = questions[2].pk
        response = self.client.post(finalize_url, {'finalize_view-current_step':'1',
                                                   '1-randomize':True})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Step 3')
        
        # Step 2 - submit
        response = self.client.post(finalize_url, {'finalize_view-current_step':'2'})
        self.assertEqual(response.status_code, 302)
        exam = Exam.objects.get(pk=exam.id)
        self.assertEqual(exam.stage, ExamStage.DIST)
        self.assertTrue(exam.randomize)
        self.assertEqual(len(exam.question_set.all()), 2)
        self.assertFalse(Question.objects.filter(pk=deleted_pk))
        self.assertEqual(questions[0].number, 1)
        self.assertEqual(questions[1].number, 1)

class CopyViewTest(SimpleTestCase):
    def setUp(self):
        get_concept_list()
        self.user = set_up_user()
        self.user.is_staff = True
        self.user.save()
        self.client.login(email=self.user.email, password='password')
    
    def test_permissions(self):
        exam = create_exam()
        exam.stage=ExamStage.DIST
        exam.kind=ExamKind.SURVEY
        exam.save()
        
        # User is staff
        response = self.client.get(reverse('survey:copy', args=[exam.id]))
        self.assertEqual(response.status_code, 200)
        
        # User logged in, not staff
        self.user.is_staff = False
        self.user.save()
        response = self.client.get(reverse('survey:copy', args=[exam.id]))
        self.assertEqual(response.status_code, 403)
        
        # User not logged in, redirected
        self.client.logout()
        response = self.client.get(reverse('survey:copy', args=[exam.id]))
        self.assertRedirects(response, '/accounts/login/?next=/exams/survey/dist/%s/copy/'%exam.id)
    
    def test_dispatch(self):
        exam = create_exam() #stage=DEV
        exam.kind = ExamKind.SURVEY
        exam.save()
        
        # exam id does not exist
        response = self.client.get(reverse('survey:copy', args=[99]))
        self.assertEqual(response.status_code, 404)
        
        # exam.can_develop() raises PermissionDenied
        response = self.client.get(reverse('survey:copy', args=[exam.id]))
        self.assertEqual(response.status_code, 403)
        
        exam.stage = ExamStage.DIST
        exam.save()
        
        # exam.kind does not match namespace
        response = self.client.get(reverse('CI_exam:copy', args=[exam.id]))
        self.assertEqual(response.status_code, 403)
        
        CI = create_exam() #stage=DEV, kind=CI
        CI2 = create_exam()
        CI2.stage = ExamStage.DIST
        CI2.save()
        response = self.client.get(reverse('CI_exam:copy', args=[CI2.id]))
        self.assertRedirects(response, reverse('CI_exam:copy_denied', args=[CI2.id]))
    
    def test_form_valid(self):
        exam = create_exam()
        exam.kind = ExamKind.SURVEY
        exam.stage = ExamStage.DIST
        exam.save()
        
        response = self.client.post(reverse('survey:copy', args=[exam.id]),
                                    {'name':'Copied Exam',
                                     'description':'a copy'})
        self.assertEqual(response.status_code, 302)
        
        self.assertTrue(Exam.objects.filter(name = "Copied Exam"))
        new_exam = Exam.objects.get(name = "Copied Exam")
        
        new_fr_questions = new_exam.freeresponsequestion_set.all()
        old_fr_questions = exam.freeresponsequestion_set.all()
        self.assertEqual(len(new_fr_questions), len(old_fr_questions))
        for i in range(0,len(new_fr_questions)):
            self.assertNotEqual(new_fr_questions[i],
                                old_fr_questions[i])
            self.assertEqual(new_fr_questions[i].question,
                             old_fr_questions[i].question)
            # make sure no old version objects were copied
            self.assertEqual(len(reversion.get_for_object(new_fr_questions[i])),1)
            
        new_mc_questions = new_exam.multiplechoicequestion_set.all()
        old_mc_questions = exam.multiplechoicequestion_set.all()
        self.assertEqual(len(new_mc_questions), len(old_mc_questions))
        for i in range(0,len(new_mc_questions)):
            self.assertNotEqual(new_mc_questions[i],
                                old_mc_questions[i])
            self.assertEqual(new_mc_questions[i].question,
                             old_mc_questions[i].question)
            self.assertEqual(new_mc_questions[i].correct_option.text,
                             old_mc_questions[i].correct_option.text)
            # make sure no old version objects were copied
            self.assertEqual(len(reversion.get_for_object(new_mc_questions[i])),1)
            
            new_options = new_mc_questions[i].multiplechoiceoption_set.all()
            old_options = old_mc_questions[i].multiplechoiceoption_set.all()
            self.assertEqual(len(new_options), len(old_options))
            for j in range(0, len(new_options)):
                self.assertNotEqual(new_options[j],
                                    old_options[j])
                self.assertEqual(new_options[j].text,
                                 old_options[j].text)


class DistIndexViewTest(SimpleTestCase):
    def setUp(self):
        self.user = set_up_user()
        self.client.login(email=self.user.email, password='password')
    
    def test_permissions(self):
        # User logged in, not contrib
        response = self.client.get(reverse('CI_exam:distribute_index'))
        self.assertEqual(response.status_code, 200)
        
        # User not logged in, redirected
        self.client.logout()
        response = self.client.get(reverse('CI_exam:distribute_index'))
        self.assertRedirects(response, '/accounts/login/?next=/exams/CI/dist/')
    
    def test_empty(self):
        for exam in Exam.objects.all():
            exam.delete()
        response = self.client.get(reverse('CI_exam:distribute_index'))
        self.assertContains(response, 'There are no CIs available for distribution.')
        self.assertContains(response, 'There are no closed CIs.')
    
    def test_dist_exam(self):
        exam, created = Exam.objects.get_or_create(name="Dist Index View Exam",
                                                   description="...",
                                                   stage=ExamStage.DIST)
        response = self.client.get(reverse('CI_exam:distribute_index'))
        self.assertContains(response, exam.name)
        
    def test_closed_exam(self):
        exam, created = Exam.objects.get_or_create(name="Dist Index View Exam",
                                                   description="...",
                                                   stage=ExamStage.CLOSED)
        response = self.client.get(reverse('CI_exam:distribute_index'))
        self.assertContains(response, exam.name)


class DistDetailViewTest(SimpleTestCase):
    def setUp(self):
        self.user = set_up_user()
        self.client.login(email=self.user.email, password='password')
        self.exam, created = Exam.objects.get_or_create(name="Dist Detail View Exam",
                                                        description="...",
                                                        stage=ExamStage.DIST)
        self.detail_url = reverse('CI_exam:distribute_detail', args=[self.exam.id])
    
    def test_permissions(self):
        # User logged in, not contrib
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        
        # Exam does not exist
        response = self.client.get(reverse('CI_exam:distribute_detail', args=[99]))
        self.assertEqual(response.status_code, 404)
        
        # User not logged in, redirected
        self.client.logout()
        response = self.client.get(self.detail_url)
        self.assertRedirects(response, '/accounts/login/?next=/exams/CI/dist/%d/' % self.exam.id)
    
    def test_staff_buttons(self):
        response = self.client.get(self.detail_url)
        self.assertNotContains(response, 'Make a copy')
        self.assertNotContains(response, 'Close Survey Distribution')
        
        self.user.is_staff = True
        self.user.save()
        response = self.client.get(self.detail_url)
        self.assertContains(response, 'Make a copy')
        self.assertContains(response, 'Close CI Distribution')
    
    def test_questions(self):
        exam = create_exam()
        exam.stage = ExamStage.DIST
        exam.save()
        response = self.client.get(reverse('CI_exam:distribute_detail', args=[exam.id]))
        for question in exam.question_set.all():
            self.assertContains(response, question)
            if question.is_multiple_choice:
                for option in question.multiplechoiceoption_set.all():
                    self.assertContains(response, option)


class ResponseSetIndexViewTest(SimpleTestCase):
    def setUp(self):
        self.user = set_up_user()
        self.client.login(email=self.user.email, password='password')
        self.exam, created = Exam.objects.get_or_create(name="RS Index View Exam",
                                                        description="...",
                                                        stage=ExamStage.DIST)
        #self.response_set, created = ResponseSet.objects.get_or_create()
        self.url = reverse('CI_exam:response_sets', args=[self.exam.id])
    
    def test_permissions(self):
        # User logged in, not contrib
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        # Exam does not exist
        response = self.client.get(reverse('CI_exam:response_sets', args=[99]))
        self.assertEqual(response.status_code, 404)
        
        # User not logged in, redirected
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, '/accounts/login/?next=/exams/CI/dist/%d/responses/' % self.exam.id)
        
    def test_empty(self):
        for set in ResponseSet.objects.all():
            set.delete()
        response = self.client.get(self.url)
        self.assertContains(response, 'This CI has not been distributed')
    
    def test_dist_exam(self):
        set, created = ResponseSet.objects.get_or_create(course='Index View RS',
                                                         exam=self.exam,
                                                         instructor=self.user.profile)
        response = self.client.get(self.url)
        self.assertContains(response, set.course)


class ResponseSetDetailViewTest(SimpleTestCase):
    def setUp(self):
        self.user = set_up_user()
        self.client.login(email=self.user.email, password='password')
        self.exam, created = Exam.objects.get_or_create(name="RS Detail View Exam",
                                                        description="...",
                                                        stage=ExamStage.DIST)
        self.set, created = ResponseSet.objects.get_or_create(course='Detail View RS',
                                                              exam=self.exam,
                                                              instructor=self.user.profile)
        self.url = reverse('CI_exam:responses', args=[self.set.id])
    
    def test_permissions(self):
        # User logged in, not contrib
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        # Exam does not exist
        response = self.client.get(reverse('CI_exam:responses', args=[99]))
        self.assertEqual(response.status_code, 404)
        
        # User not logged in, redirected
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, '/accounts/login/?next=/exams/CI/dist/response_set/%d/' % self.set.id)


class ExamResponseDetailViewTest(SimpleTestCase):
    def setUp(self):
        self.user = set_up_user()
        self.client.login(email=self.user.email, password='password')
        self.exam, created = Exam.objects.get_or_create(name="ER Detail View Exam",
                                                        description="...",
                                                        stage=ExamStage.DIST)
        self.set, created = ResponseSet.objects.get_or_create(course='ER Detail View RS',
                                                         exam=self.exam,
                                                         instructor=self.user.profile)
        self.response = ExamResponse.objects.create(response_set=self.set,
                                                                    expiration_datetime=timezone.now())
        self.url = reverse('CI_exam:response_detail', args=[self.response.pk])
    
    def test_permissions(self):
        # User logged in, not contrib
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        # Exam does not exist
        response = self.client.get(reverse('CI_exam:response_detail', args=[99]))
        self.assertEqual(response.status_code, 404)
        
        # User not logged in, redirected
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, '/accounts/login/?next=/exams/CI/dist/response/%s/' % self.response.pk)
    
    def test_unsubmitted(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'has not been submitted yet')


class NewResponseSetViewTest(SimpleTestCase):
    def setUp(self):
        self.user = set_up_user()
        self.client.login(email=self.user.email, password='password')
        self.exam, created = Exam.objects.get_or_create(name="RS Detail View Exam",
                                                        description="...",
                                                        stage=ExamStage.DIST)
        self.url = reverse('CI_exam:distribute_new', args=[self.exam.id])
        
    def test_permissions(self):
        # User logged in, not contrib
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        # Exam does not exist
        response = self.client.get(reverse('CI_exam:distribute_new', args=[99]))
        self.assertEqual(response.status_code, 404)
        
        # User not logged in, redirected
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, '/accounts/login/?next=/exams/CI/dist/%d/new/' % self.exam.id)
    
    def test_previous_distributions(self):
        # emtpy
        # not empty
        pass
    
    def test_submit_form(self):
        pass


class DistributeViewTest(SimpleTestCase):
    #setUP
    #permissions
    
    def test_submitted_exams(self):
        #empty
        #not empty
        pass
    
    def test_submit_form(self):
        #redirect
        #create exam
        pass


class DeleteViewTest(SimpleTestCase):
    #setUp
    #permissions
    
    def test_delete(self):
        pass
    

class CleanupViewTest(SimpleTestCase):
    #setUp
    #permissions
    
    def test_clean_up(self):
        pass


class IntegratedDistributionTest(SimpleTestCase):
    def test_ordered(self):
        # new response set
        # distribute
        # take test
        # view results
        pass
    
    def test_randomized(self):
        pass
    
    