using System.ComponentModel.DataAnnotations;
using BookApi.Domain;

namespace BookApi.Api;

public record AuthorResponse(long Id, string Name, string Nationality, int BirthYear)
{
    public static AuthorResponse Of(Author a) =>
        new(a.Id, a.Name, a.Nationality, a.BirthYear);
}

public record BookResponse(long Id, string Title, string Isbn, int PublicationYear,
    decimal Price, DateTimeOffset CreatedAt, AuthorResponse Author)
{
    public static BookResponse Of(Book b) =>
        new(b.Id, b.Title, b.Isbn, b.PublicationYear, b.Price, b.CreatedAt,
            AuthorResponse.Of(b.Author));
}

public record PageResponse(int Page, int Size, IReadOnlyList<BookResponse> Content);

public record SearchResponse(int Size, IReadOnlyList<BookResponse> Content);

public record Violation(string Field, string Message);

public record ApiError(int Status, string Message, IReadOnlyList<Violation>? Violations = null);

// O EF Core grava em NUMERIC(10,2) arredondando em silêncio; sem esta verificação o
// contrato de "no máximo 2 casas decimais" (seção 4.4) não seria aplicado. Os demais
// frameworks obtém a mesma regra de seus validadores nativos (@Digits, DecimalField,
// maxDecimalPlaces, decimal:0,2) — a assimetria é própria do ecossistema e conta como tal
// na métrica de produtividade da seção 7.
public class DecimalPlacesAttribute(int places) : ValidationAttribute
{
    public override bool IsValid(object? value) =>
        value is not decimal d || decimal.Round(d, places) == d;
}

public record BookRequest(
    [Required, Range(1, long.MaxValue)] long? AuthorId,
    [Required(AllowEmptyStrings = false), StringLength(200, MinimumLength = 1)] string? Title,
    [Required, RegularExpression(@"^[0-9]{13}$")] string? Isbn,
    [Required, Range(1450, 2100)] int? PublicationYear,
    [Required, Range(typeof(decimal), "0", "99999999.99", ParseLimitsInInvariantCulture = true),
        DecimalPlaces(2)] decimal? Price);

public record BookUpdateRequest(
    [Required(AllowEmptyStrings = false), StringLength(200, MinimumLength = 1)] string? Title,
    [Required, Range(1450, 2100)] int? PublicationYear,
    [Required, Range(typeof(decimal), "0", "99999999.99", ParseLimitsInInvariantCulture = true),
        DecimalPlaces(2)] decimal? Price);
