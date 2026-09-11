using System.Text.Json.Serialization;
using BookApi.Api;
using BookApi.Domain;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

// Pool fixo em 10 conexões (seção 6.1). O padrão do Npgsql é 0..100; deixá-lo livre
// significaria medir a decisão de configuração do driver, e não o framework.
var connectionString =
    $"Host={Env("DB_HOST", "localhost")};Port={Env("DB_PORT", "5432")};" +
    $"Database={Env("DB_NAME", "tccbench")};Username={Env("DB_USER", "bench")};" +
    $"Password={Env("DB_PASSWORD", "bench")};" +
    "Minimum Pool Size=10;Maximum Pool Size=10";

builder.Services.AddDbContext<BookDbContext>(options => options.UseNpgsql(connectionString));

builder.Services.AddControllers()
    .AddJsonOptions(options => options.JsonSerializerOptions.DefaultIgnoreCondition =
        JsonIgnoreCondition.WhenWritingNull);

// Corpo de erro único às cinco implementações (seção 5.2), no lugar do ProblemDetails que
// o atributo [ApiController] devolveria por padrão.
builder.Services.Configure<ApiBehaviorOptions>(options =>
    options.InvalidModelStateResponseFactory = context =>
    {
        var violations = context.ModelState
            .Where(entry => entry.Value is { Errors.Count: > 0 })
            .Select(entry => new Violation(FieldName(entry.Key), entry.Value!.Errors[0].ErrorMessage))
            .ToList();
        return new ObjectResult(new ApiError(400, "Validation failed", violations)) { StatusCode = 400 };
    });

var app = builder.Build();

app.MapControllers();

app.Run();

static string Env(string key, string fallback) =>
    Environment.GetEnvironmentVariable(key) is { Length: > 0 } value ? value : fallback;

// As chaves do ModelState chegam como "Title" (validação) ou "$.title" (desserialização);
// os nomes de campo do corpo de erro são camelCase em todas as implementações (seção 3).
static string FieldName(string key)
{
    var name = key.StartsWith("$.") ? key[2..] : key;
    return name.Length == 0 ? name : char.ToLowerInvariant(name[0]) + name[1..];
}
