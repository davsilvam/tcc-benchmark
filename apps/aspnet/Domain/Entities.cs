namespace BookApi.Domain;

public class Author
{
    public long Id { get; set; }
    public string Name { get; set; } = "";
    public string Nationality { get; set; } = "";
    public int BirthYear { get; set; }
}

public class Book
{
    public long Id { get; set; }
    public long AuthorId { get; set; }
    public Author Author { get; set; } = null!;
    public string Title { get; set; } = "";
    public string Isbn { get; set; } = "";
    public int PublicationYear { get; set; }
    public decimal Price { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
}
