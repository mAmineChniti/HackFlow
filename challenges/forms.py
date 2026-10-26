from django import forms

from .models import Challenge, ChallengeQuestion, ChallengeSubmission, ChallengeAnswer


class ChallengeForm(forms.ModelForm):
    class Meta:
        model = Challenge
        fields = ["title", "description", "category", "difficulty", "points", "status", "hackathon"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "title": forms.TextInput(attrs={"placeholder": "Ex: Rate Limit Bypass"}),
            "category": forms.TextInput(attrs={"placeholder": "Ex: Web Security, AI / ML"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Textarea):
                widget.attrs["class"] = (
                    "flex min-h-[90px] w-full rounded-md border border-input bg-transparent "
                    "px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground "
                    "focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
                )
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = (
                    "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 "
                    "text-sm shadow-xs focus-visible:outline-hidden focus-visible:ring-1 "
                    "focus-visible:ring-ring"
                )
            else:
                widget.attrs["class"] = (
                    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 "
                    "text-sm shadow-xs placeholder:text-muted-foreground "
                    "focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
                )


class ChallengeQuestionForm(forms.ModelForm):
    class Meta:
        model = ChallengeQuestion
        fields = ["question_text", "answer_type", "correct_answer", "points", "order", "hint"]
        widgets = {
            "question_text": forms.Textarea(attrs={"rows": 3}),
            "correct_answer": forms.TextInput(attrs={"placeholder": "Ex: flag{hidden_secret}"}),
            "hint": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional hint for participants"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Textarea):
                widget.attrs["class"] = (
                    "flex min-h-[80px] w-full rounded-md border border-input bg-transparent "
                    "px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground "
                    "focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
                )
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = (
                    "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 "
                    "text-sm shadow-xs focus-visible:outline-hidden focus-visible:ring-1 "
                    "focus-visible:ring-ring"
                )
            else:
                widget.attrs["class"] = (
                    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 "
                    "text-sm shadow-xs placeholder:text-muted-foreground "
                    "focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
                )


class ChallengeQuestionFormSetHelper:
    pass


class ChallengeSubmissionForm(forms.Form):
    def __init__(self, *args, challenge=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.challenge = challenge
        if challenge:
            questions = challenge.questions.all().order_by("order", "id")
            for question in questions:
                field_name = f"question_{question.id}"
                placeholder = "Enter your answer"
                if question.answer_type == ChallengeQuestion.AnswerType.FLAG:
                    placeholder = "Ex: flag{...}"
                elif question.answer_type == ChallengeQuestion.AnswerType.NUMBER:
                    placeholder = "Enter a number"
                self.fields[field_name] = forms.CharField(
                    label=f"Q{question.order + 1}: {question.question_text}",
                    required=True,
                    widget=forms.TextInput(attrs={"placeholder": placeholder}),
                )
                self.fields[field_name].widget.attrs["class"] = (
                    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 "
                    "text-sm shadow-xs placeholder:text-muted-foreground "
                    "focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring font-mono"
                )
