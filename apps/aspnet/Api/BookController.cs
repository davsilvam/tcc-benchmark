using BookApi.Domain;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace BookApi.Api;

[ApiController]
[Route("api")]
public class BookController(BookDbContext db) : ControllerBase
{
    [HttpGet("health")]
    public IActionResult Health() => Ok(new Dictionary<string, string> { ["status"] = "UP" });

    [HttpGet("books")]
    public async Task<IActionResult> List([FromQuery] string? page, [FromQuery] string? size)
    {
        if (!TryPositiveInt(page, 0, 0, int.MaxValue, out var p)) return Invalid("page");
        if (!TryPositiveInt(size, 20, 1, 100, out var s)) return Invalid("size");

        // Include de uma associação *-para-um produz UMA instrução com INNER JOIN. Sem ele,
        // o carregamento tardio traria uma consulta por item (problema N+1) e violaria o
        // critério de aceite 8.2.
        var books = await db.Books.AsNoTracking()
            .Include(b => b.Author)
            .OrderBy(b => b.Id)
            .Skip(p * s).Take(s)
            .ToListAsync();

        return Ok(new PageResponse(p, s, books.Select(BookResponse.Of).ToList()));
    }

    [HttpGet("books/search")]
    public async Task<IActionResult> Search([FromQuery] string? title, [FromQuery] string? size)
    {
        if (string.IsNullOrWhiteSpace(title) || title.Length > 200) return Invalid("title");
        if (!TryPositiveInt(size, 20, 1, 100, out var s)) return Invalid("size");

        // Ordenação por title, e não por id: sob COLLATE "C" o índice idx_books_title atende
        // ao filtro por prefixo e à ordenação na mesma varredura de intervalo (seção 4.3).
        var prefix = title + "%";
        var books = await db.Books.AsNoTracking()
            .Include(b => b.Author)
            .Where(b => EF.Functions.Like(b.Title, prefix))
            .OrderBy(b => b.Title)
            .Take(s)
            .ToListAsync();

        return Ok(new SearchResponse(s, books.Select(BookResponse.Of).ToList()));
    }

    // O identificador chega como texto para que um valor não numérico produza 400, e não o
    // 404 que uma restrição de rota {id:long} devolveria.
    [HttpGet("books/{id}")]
    public async Task<IActionResult> ById(string id)
    {
        if (!long.TryParse(id, out var bookId)) return Invalid("id");

        var book = await db.Books.AsNoTracking()
            .Include(b => b.Author)
            .FirstOrDefaultAsync(b => b.Id == bookId);

        return book is null ? NotFound(new ApiError(404, "Resource not found"))
                            : Ok(BookResponse.Of(book));
    }

    [HttpPost("books")]
    public async Task<IActionResult> Create([FromBody] BookRequest request)
    {
        // Existência do autor verificada explicitamente (1 SELECT), e não delegada a
        // violação de chave estrangeira: o tratamento de erro de integridade difere entre
        // os ORMs e produziria caminhos de execução distintos entre as implementações.
        var author = await db.Authors.FindAsync(request.AuthorId!.Value);
        if (author is null)
        {
            return BadRequest(new ApiError(400, "Validation failed",
                [new Violation("authorId", "author does not exist")]));
        }

        var book = new Book
        {
            AuthorId = author.Id,
            Author = author,
            Title = request.Title!,
            Isbn = request.Isbn!,
            PublicationYear = request.PublicationYear!.Value,
            Price = request.Price!.Value,
            CreatedAt = DateTimeOffset.UtcNow,
        };

        db.Books.Add(book);
        try
        {
            await db.SaveChangesAsync();
        }
        catch (DbUpdateException e) when (e.InnerException is PostgresException { SqlState: "23505" })
        {
            return Conflict(new ApiError(409, "isbn already exists"));
        }

        return Created($"/api/books/{book.Id}", BookResponse.Of(book));
    }

    [HttpPut("books/{id}")]
    public async Task<IActionResult> Update(string id, [FromBody] BookUpdateRequest request)
    {
        if (!long.TryParse(id, out var bookId)) return Invalid("id");

        var book = await db.Books.Include(b => b.Author).FirstOrDefaultAsync(b => b.Id == bookId);
        if (book is null) return NotFound(new ApiError(404, "Resource not found"));

        book.Title = request.Title!;
        book.PublicationYear = request.PublicationYear!.Value;
        book.Price = request.Price!.Value;
        await db.SaveChangesAsync();

        return Ok(BookResponse.Of(book));
    }

    private static bool TryPositiveInt(string? raw, int fallback, int min, int max, out int value)
    {
        value = fallback;
        if (string.IsNullOrEmpty(raw)) return true;
        return int.TryParse(raw, out value) && value >= min && value <= max;
    }

    private BadRequestObjectResult Invalid(string field) =>
        BadRequest(new ApiError(400, "Validation failed", [new Violation(field, "invalid value")]));
}
