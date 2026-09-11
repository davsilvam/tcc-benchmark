using Microsoft.EntityFrameworkCore;

namespace BookApi.Domain;

// O mapeamento é explícito porque o esquema é externo (seção 2.4 da especificação):
// nenhuma migration do EF Core é gerada ou aplicada, e o contexto apenas descreve uma
// estrutura pré-existente e idêntica à das demais implementações.
public class BookDbContext(DbContextOptions<BookDbContext> options) : DbContext(options)
{
    public DbSet<Author> Authors => Set<Author>();
    public DbSet<Book> Books => Set<Book>();

    protected override void OnModelCreating(ModelBuilder model)
    {
        model.Entity<Author>(e =>
        {
            e.ToTable("authors");
            e.HasKey(x => x.Id);
            // authors.id não é serial: os identificadores vêm da carga semente.
            e.Property(x => x.Id).HasColumnName("id").ValueGeneratedNever();
            e.Property(x => x.Name).HasColumnName("name");
            e.Property(x => x.Nationality).HasColumnName("nationality");
            e.Property(x => x.BirthYear).HasColumnName("birth_year");
        });

        model.Entity<Book>(e =>
        {
            e.ToTable("books");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").ValueGeneratedOnAdd();
            e.Property(x => x.AuthorId).HasColumnName("author_id");
            e.Property(x => x.Title).HasColumnName("title");
            e.Property(x => x.Isbn).HasColumnName("isbn").IsFixedLength().HasMaxLength(13);
            e.Property(x => x.PublicationYear).HasColumnName("publication_year");
            e.Property(x => x.Price).HasColumnName("price").HasPrecision(10, 2);
            e.Property(x => x.CreatedAt).HasColumnName("created_at");
            e.HasOne(x => x.Author).WithMany().HasForeignKey(x => x.AuthorId);
        });
    }
}
