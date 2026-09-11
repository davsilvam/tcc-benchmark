from django.db import models


# managed = False: o esquema é criado por SQL puro e nenhuma migration é gerada ou
# aplicada (seção 2.4 da especificação). Os modelos apenas mapeiam uma estrutura
# pré-existente, idêntica à das demais implementações.
class Author(models.Model):
    id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=120)
    nationality = models.CharField(max_length=60)
    birth_year = models.IntegerField()

    class Meta:
        managed = False
        db_table = "authors"


class Book(models.Model):
    id = models.BigAutoField(primary_key=True)
    author = models.ForeignKey(Author, models.DO_NOTHING, db_column="author_id")
    title = models.CharField(max_length=200)
    isbn = models.CharField(max_length=13)
    publication_year = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "books"
