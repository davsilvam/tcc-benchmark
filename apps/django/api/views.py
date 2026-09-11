import json
from datetime import datetime, timezone

from django.db import IntegrityError
from django.http import JsonResponse

from .forms import BookForm, BookUpdateForm
from .models import Author, Book

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


# --- representações (seção 5) --------------------------------------------------------


def author_json(author):
    return {
        "id": author.id,
        "name": author.name,
        "nationality": author.nationality,
        "birthYear": author.birth_year,
    }


def book_json(book):
    # float(price) é deliberado: JsonResponse usa DjangoJSONEncoder, que serializa Decimal
    # como *string*. O contrato exige número JSON (seção 3).
    return {
        "id": book.id,
        "title": book.title,
        "isbn": book.isbn,
        "publicationYear": book.publication_year,
        "price": float(book.price),
        "createdAt": book.created_at.isoformat(),
        "author": author_json(book.author),
    }


def error(status, message, violations=None):
    body = {"status": status, "message": message}
    if violations:
        body["violations"] = violations
    return JsonResponse(body, status=status)


def form_violations(form):
    return [
        {"field": field, "message": messages[0]}
        for field, messages in form.errors.items()
    ]


def bounded_int(raw, fallback, minimum, maximum):
    """Devolve (valor, ok). Ausente => padrao; fora do intervalo ou nao numerico => erro."""
    if raw is None or raw == "":
        return fallback, True
    try:
        value = int(raw)
    except ValueError:
        return fallback, False
    return value, minimum <= value <= maximum


def parse_body(request):
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


# --- endpoints (seção 4) -------------------------------------------------------------


def health(request):
    return JsonResponse({"status": "UP"})


def books(request):
    if request.method == "POST":
        return create(request)
    if request.method != "GET":
        return error(405, "Method not allowed")

    page, ok_page = bounded_int(request.GET.get("page"), 0, 0, 2**31 - 1)
    size, ok_size = bounded_int(request.GET.get("size"), DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
    if not ok_page:
        return error(400, "Validation failed", [{"field": "page", "message": "invalid value"}])
    if not ok_size:
        return error(400, "Validation failed", [{"field": "size", "message": "invalid value"}])

    # select_related mantém a listagem em UMA instrução SQL: sem ele, o acesso a
    # book.author dispararia uma consulta por item (problema N+1) e violaria o critério
    # de aceite 8.2. O fatiamento vira LIMIT/OFFSET e não emite COUNT — o Paginator do
    # Django emitiria, e a resposta do contrato não tem totalElements (seção 4.1).
    offset = page * size
    rows = Book.objects.select_related("author").order_by("id")[offset:offset + size]

    return JsonResponse({"page": page, "size": size, "content": [book_json(b) for b in rows]})


def search(request):
    if request.method != "GET":
        return error(405, "Method not allowed")

    title = request.GET.get("title") or ""
    if not title.strip() or len(title) > 200:
        return error(400, "Validation failed", [{"field": "title", "message": "invalid value"}])

    size, ok_size = bounded_int(request.GET.get("size"), DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
    if not ok_size:
        return error(400, "Validation failed", [{"field": "size", "message": "invalid value"}])

    # __startswith (sensível a caixa) traduz-se em LIKE 'prefixo%'; __istartswith usaria
    # UPPER(...) e descartaria o índice idx_books_title (seção 4.3). A ordenação por title
    # mantém filtro e ordenação na mesma varredura de intervalo.
    rows = (
        Book.objects.select_related("author")
        .filter(title__startswith=title)
        .order_by("title")[:size]
    )

    return JsonResponse({"size": size, "content": [book_json(b) for b in rows]})


def create(request):
    payload = parse_body(request)
    if payload is None:
        return error(400, "Invalid request")

    form = BookForm(payload)
    if not form.is_valid():
        return error(400, "Validation failed", form_violations(form))

    data = form.cleaned_data

    # Existência do autor verificada explicitamente (1 SELECT), e não delegada a violação
    # de chave estrangeira: o tratamento de erro de integridade difere entre os ORMs e
    # produziria caminhos de execução distintos entre as implementações.
    author = Author.objects.filter(pk=data["authorId"]).first()
    if author is None:
        return error(400, "Validation failed",
                     [{"field": "authorId", "message": "author does not exist"}])

    try:
        book = Book.objects.create(
            author=author,
            title=data["title"],
            isbn=data["isbn"],
            publication_year=data["publicationYear"],
            price=data["price"],
            created_at=datetime.now(timezone.utc),
        )
    except IntegrityError:
        return error(409, "isbn already exists")

    response = JsonResponse(book_json(book), status=201)
    response["Location"] = f"/api/books/{book.id}"
    return response


def book_detail(request, book_id):
    # O identificador chega como texto para que um valor não numérico produza 400, e não o
    # 404 que o conversor de rota <int:...> devolveria.
    try:
        pk = int(book_id)
    except ValueError:
        return error(400, "Validation failed", [{"field": "id", "message": "invalid value"}])

    if request.method == "GET":
        book = Book.objects.select_related("author").filter(pk=pk).first()
        if book is None:
            return error(404, "Resource not found")
        return JsonResponse(book_json(book))

    if request.method != "PUT":
        return error(405, "Method not allowed")

    payload = parse_body(request)
    if payload is None:
        return error(400, "Invalid request")

    form = BookUpdateForm(payload)
    if not form.is_valid():
        return error(400, "Validation failed", form_violations(form))

    book = Book.objects.select_related("author").filter(pk=pk).first()
    if book is None:
        return error(404, "Resource not found")

    data = form.cleaned_data
    book.title = data["title"]
    book.publication_year = data["publicationYear"]
    book.price = data["price"]
    # update_fields restringe o UPDATE às três colunas do contrato (seção 4.5).
    book.save(update_fields=["title", "publication_year", "price"])

    return JsonResponse(book_json(book))
