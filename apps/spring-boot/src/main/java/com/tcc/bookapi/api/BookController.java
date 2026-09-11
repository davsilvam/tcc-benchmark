package com.tcc.bookapi.api;

import com.tcc.bookapi.domain.Author;
import com.tcc.bookapi.domain.AuthorRepository;
import com.tcc.bookapi.domain.Book;
import com.tcc.bookapi.domain.BookRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
@Validated
class BookController {

    private final BookRepository books;
    private final AuthorRepository authors;

    BookController(BookRepository books, AuthorRepository authors) {
        this.books = books;
        this.authors = authors;
    }

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "UP");
    }

    @GetMapping("/books")
    PageResponse list(@RequestParam(defaultValue = "0") @Min(0) int page,
                      @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        List<BookResponse> content = books.findPage(PageRequest.of(page, size))
                .stream().map(BookResponse::of).toList();
        return new PageResponse(page, size, content);
    }

    @GetMapping("/books/{id}")
    BookResponse byId(@PathVariable long id) {
        return books.findDetailById(id).map(BookResponse::of).orElseThrow(NotFoundException::new);
    }

    @GetMapping("/books/search")
    SearchResponse search(@RequestParam @NotBlank String title,
                          @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        List<BookResponse> content = books.findByTitlePrefix(title, PageRequest.of(0, size))
                .stream().map(BookResponse::of).toList();
        return new SearchResponse(size, content);
    }

    // @Transactional é requisito de contagem, não conveniência. Sem ele, a busca do autor e
    // a gravação do livro ocorrem em contextos de persistência distintos: o autor chega
    // DESTACADO a books.save(), e o Hibernate emite um SELECT adicional sobre authors para
    // reassociá-lo — três instruções onde o contrato exige duas (seção 4.4).
    @PostMapping("/books")
    @Transactional
    ResponseEntity<BookResponse> create(@RequestBody @Valid BookRequest request) {
        // Existência do autor verificada explicitamente (1 SELECT), e não delegada a
        // violação de chave estrangeira: o tratamento de erro de integridade difere entre
        // os ORMs e produziria caminhos de execução distintos entre as implementações.
        Author author = authors.findById(request.authorId())
                .orElseThrow(() -> new BadRequestException("authorId does not exist"));

        Book book = books.save(new Book(author, request.title(), request.isbn(),
                request.publicationYear(), request.price()));

        return ResponseEntity.created(URI.create("/api/books/" + book.getId()))
                .body(BookResponse.of(book));
    }

    @PutMapping("/books/{id}")
    @Transactional
    BookResponse update(@PathVariable long id, @RequestBody @Valid BookUpdateRequest request) {
        Book book = books.findDetailById(id).orElseThrow(NotFoundException::new);
        book.update(request.title(), request.publicationYear(), request.price());
        return BookResponse.of(book);
    }
}
