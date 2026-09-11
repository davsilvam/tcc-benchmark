from django import forms

# A validação usa django.forms, recurso de primeira parte do framework: nenhuma biblioteca
# externa de serialização é utilizada, em coerência com a regra da seção 7 da especificação.
# Os nomes dos campos são camelCase porque espelham o corpo JSON do contrato (seção 3).


class BookForm(forms.Form):
    authorId = forms.IntegerField(min_value=1)
    title = forms.CharField(min_length=1, max_length=200)
    isbn = forms.RegexField(regex=r"^[0-9]{13}$")
    publicationYear = forms.IntegerField(min_value=1450, max_value=2100)
    price = forms.DecimalField(min_value=0, max_digits=10, decimal_places=2)


class BookUpdateForm(forms.Form):
    title = forms.CharField(min_length=1, max_length=200)
    publicationYear = forms.IntegerField(min_value=1450, max_value=2100)
    price = forms.DecimalField(min_value=0, max_digits=10, decimal_places=2)
