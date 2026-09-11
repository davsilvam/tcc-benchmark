<?php

namespace App\Http\Controllers;

use App\Models\Author;
use App\Models\Book;
use Illuminate\Database\QueryException;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\ValidationException;

class BookController extends Controller
{
    private const DEFAULT_PAGE_SIZE = 20;

    private const MAX_PAGE_SIZE = 100;

    private const MAX_TITLE_LENGTH = 200;

    // O eager loading do Eloquent (with('author')) emite DUAS instruções: uma para os
    // livros e outra para os autores. O contrato exige exatamente uma por requisição de
    // leitura (seção 4), portanto a junção é explícita e as colunas do autor vêm com
    // alias na mesma consulta.
    private const COLUMNS = [
        'books.id',
        'books.title',
        'books.isbn',
        'books.publication_year',
        'books.price',
        'books.created_at',
        'authors.id as author_id',
        'authors.name as author_name',
        'authors.nationality as author_nationality',
        'authors.birth_year as author_birth_year',
    ];

    public function health(): JsonResponse
    {
        return response()->json(['status' => 'UP']);
    }

    public function index(Request $request): JsonResponse
    {
        $page = $this->boundedInt($request->query('page'), 0, 0, PHP_INT_MAX, 'page');
        $size = $this->boundedInt($request->query('size'), self::DEFAULT_PAGE_SIZE, 1, self::MAX_PAGE_SIZE, 'size');

        $books = $this->joinedQuery()
            ->orderBy('books.id')
            ->offset($page * $size)
            ->limit($size)
            ->get();

        return response()->json([
            'page' => $page,
            'size' => $size,
            'content' => $books->map(fn (Book $book) => $this->joinedPayload($book))->all(),
        ]);
    }

    public function search(Request $request): JsonResponse
    {
        $title = $request->query('title');
        if (! is_string($title) || trim($title) === '' || mb_strlen($title) > self::MAX_TITLE_LENGTH) {
            throw $this->invalid('title');
        }

        $size = $this->boundedInt($request->query('size'), self::DEFAULT_PAGE_SIZE, 1, self::MAX_PAGE_SIZE, 'size');

        // LIKE simples, sensível a maiúsculas: ILIKE ou UPPER(...) descartariam o índice
        // idx_books_title. A ordenação por title — e não por id — mantém filtro e
        // ordenação na mesma varredura de intervalo, sob COLLATE "C" (seção 4.3).
        $books = $this->joinedQuery()
            ->where('books.title', 'like', $title.'%')
            ->orderBy('books.title')
            ->limit($size)
            ->get();

        return response()->json([
            'size' => $size,
            'content' => $books->map(fn (Book $book) => $this->joinedPayload($book))->all(),
        ]);
    }

    public function show(string $id): JsonResponse
    {
        $book = $this->findWithAuthor($id);
        if ($book === null) {
            abort(404, 'Resource not found');
        }

        return response()->json($this->joinedPayload($book));
    }

    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'authorId' => ['required', 'integer', 'min:1'],
            'title' => ['required', 'string', 'min:1', 'max:200'],
            'isbn' => ['required', 'string', 'regex:/^[0-9]{13}$/'],
            'publicationYear' => ['required', 'integer', 'min:1450', 'max:2100'],
            'price' => ['required', 'numeric', 'min:0', 'decimal:0,2'],
        ]);

        // Existência do autor verificada explicitamente (1 SELECT), e não delegada a
        // violação de chave estrangeira: o tratamento de erro de integridade difere entre
        // os ORMs e produziria caminhos de execução distintos entre as implementações.
        $author = Author::query()->find($data['authorId']);
        if ($author === null) {
            throw ValidationException::withMessages(['authorId' => 'author does not exist']);
        }

        try {
            $book = Book::query()->create([
                'author_id' => $author->id,
                'title' => $data['title'],
                'isbn' => $data['isbn'],
                'publication_year' => $data['publicationYear'],
                'price' => $data['price'],
                'created_at' => now(),
            ]);
        } catch (QueryException $exception) {
            if ($exception->getCode() === '23505') {
                return response()->json(['status' => 409, 'message' => 'isbn already exists'], 409);
            }
            throw $exception;
        }

        return response()
            ->json($this->payload($book, $this->authorPayload($author)), 201)
            ->header('Location', '/api/books/'.$book->id);
    }

    public function update(Request $request, string $id): JsonResponse
    {
        // authorId não é atualizável: validar um novo autor exigiria uma terceira consulta
        // e o número de instruções passaria a depender do corpo da requisição (seção 4.5).
        $data = $request->validate([
            'title' => ['required', 'string', 'min:1', 'max:200'],
            'publicationYear' => ['required', 'integer', 'min:1450', 'max:2100'],
            'price' => ['required', 'numeric', 'min:0', 'decimal:0,2'],
        ]);

        $book = $this->findWithAuthor($id);
        if ($book === null) {
            abort(404, 'Resource not found');
        }

        // Atualização pelo construtor de consultas, e não $book->save(): o modelo foi
        // hidratado com colunas do autor sob alias, e save() tentaria gravá-las.
        Book::query()->where('id', (int) $id)->update([
            'title' => $data['title'],
            'publication_year' => $data['publicationYear'],
            'price' => $data['price'],
        ]);

        $book->title = $data['title'];
        $book->publication_year = $data['publicationYear'];
        $book->price = $data['price'];

        return response()->json($this->joinedPayload($book));
    }

    private function joinedQuery()
    {
        return Book::query()
            ->join('authors', 'authors.id', '=', 'books.author_id')
            ->select(self::COLUMNS);
    }

    private function findWithAuthor(string $id): ?Book
    {
        // O identificador chega como texto para que um valor não numérico produza 400, e
        // não o 404 que uma restrição de rota devolveria.
        if (! ctype_digit($id)) {
            throw $this->invalid('id');
        }

        return $this->joinedQuery()->where('books.id', (int) $id)->first();
    }

    private function joinedPayload(Book $book): array
    {
        return $this->payload($book, [
            'id' => (int) $book->author_id,
            'name' => $book->author_name,
            'nationality' => $book->author_nationality,
            'birthYear' => (int) $book->author_birth_year,
        ]);
    }

    private function authorPayload(Author $author): array
    {
        return [
            'id' => (int) $author->id,
            'name' => $author->name,
            'nationality' => $author->nationality,
            'birthYear' => (int) $author->birth_year,
        ];
    }

    private function payload(Book $book, array $author): array
    {
        return [
            'id' => (int) $book->id,
            'title' => $book->title,
            'isbn' => $book->isbn,
            'publicationYear' => (int) $book->publication_year,
            'price' => (float) $book->price,
            'createdAt' => $book->created_at->toIso8601String(),
            'author' => $author,
        ];
    }

    private function boundedInt(mixed $raw, int $fallback, int $min, int $max, string $field): int
    {
        if ($raw === null || $raw === '') {
            return $fallback;
        }
        if (! is_string($raw) || ! ctype_digit(ltrim($raw, '-'))) {
            throw $this->invalid($field);
        }

        $value = (int) $raw;
        if ($value < $min || $value > $max) {
            throw $this->invalid($field);
        }

        return $value;
    }

    private function invalid(string $field): ValidationException
    {
        return ValidationException::withMessages([$field => 'invalid value']);
    }
}
