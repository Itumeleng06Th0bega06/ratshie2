"""Public-facing forms for the product catalogue (currently: product reviews)."""
from django import forms

from .models import ProductReview


class ProductReviewForm(forms.ModelForm):
    """Member review of a product.

    `rating` uses a hidden widget because the star picker on the page renders
    its own radio group with the same name; the field still exists so its value
    is validated server-side (an IntegerField with 1-5 choices) and errors
    render next to the picker.
    """

    class Meta:
        model = ProductReview
        fields = ("rating", "title", "comment")
        widgets = {
            "rating": forms.HiddenInput(),
            "title": forms.TextInput(attrs={"placeholder": "Add a short headline (optional)"}),
            "comment": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Tell us about the fit, quality, delivery or performance…",
                }
            ),
        }
        labels = {
            "title": "Headline (optional)",
            "comment": "Your review",
        }

    def clean_comment(self):
        """Require a few words so the review is genuinely useful to buyers."""
        comment = (self.cleaned_data.get("comment") or "").strip()
        if len(comment) < 5:
            raise forms.ValidationError("Please write at least a short sentence for your review.")
        return comment