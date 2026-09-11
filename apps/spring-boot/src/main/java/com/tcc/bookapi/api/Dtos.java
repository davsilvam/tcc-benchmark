package com.tcc.bookapi.api;

import com.tcc.bookapi.domain.Author;
import com.tcc.bookapi.domain.Book;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;

record AuthorResponse(Long id, String name, String nationality, Integer birthYear) {

    static AuthorResponse of(Author a) {
        return new AuthorResponse(a.getId(), a.getName(), a.getNationality(), a.getBirthYear());
    }
}

record BookResponse(Long id, String title, String isbn, Integer publicationYear,
                    BigDecimal price, OffsetDateTime createdAt, AuthorResponse author) {

    static BookResponse of(Book b) {
        return new BookResponse(b.getId(), b.getTitle(), b.getIsbn(), b.getPublicationYear(),
                b.getPrice(), b.getCreatedAt(), AuthorResponse.of(b.getAuthor()));
    }
}

record PageResponse(int page, int size, List<BookResponse> content) {
}

record SearchResponse(int size, List<BookResponse> content) {
}

record BookRequest(
        @NotNull @Positive Long authorId,
        @NotBlank @Size(max = 200) String title,
        @NotNull @Pattern(regexp = "\\d{13}") String isbn,
        @NotNull @Min(1450) @Max(2100) Integer publicationYear,
        @NotNull @DecimalMin("0.0") @Digits(integer = 8, fraction = 2) BigDecimal price) {
}

record BookUpdateRequest(
        @NotBlank @Size(max = 200) String title,
        @NotNull @Min(1450) @Max(2100) Integer publicationYear,
        @NotNull @DecimalMin("0.0") @Digits(integer = 8, fraction = 2) BigDecimal price) {
}

record Violation(String field, String message) {
}

record ApiError(int status, String message, List<Violation> violations) {

    static ApiError of(int status, String message) {
        return new ApiError(status, message, null);
    }
}
