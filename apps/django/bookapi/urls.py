from django.urls import path

from api import views

# A rota literal books/search precede books/<id>: o Django resolve na ordem da lista.
urlpatterns = [
    path("api/health", views.health),
    path("api/books", views.books),
    path("api/books/search", views.search),
    path("api/books/<str:book_id>", views.book_detail),
]
