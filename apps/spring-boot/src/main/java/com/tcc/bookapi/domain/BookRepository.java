package com.tcc.bookapi.domain;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface BookRepository extends JpaRepository<Book, Long> {

    // join fetch mantém a listagem em UMA instrução SQL: sem ele, o carregamento tardio
    // do autor produziria uma consulta adicional por item (problema N+1), violando o
    // critério de aceite 8.2 da especificação funcional.
    @Query("select b from Book b join fetch b.author order by b.id")
    List<Book> findPage(Pageable pageable);

    @Query("select b from Book b join fetch b.author where b.id = :id")
    Optional<Book> findDetailById(@Param("id") Long id);

    // Ordenação por título, e não por id: sob COLLATE "C" o índice idx_books_title atende
    // ao filtro por prefixo e à ordenação na mesma varredura de intervalo. Ordenar por id
    // levaria o planejador a varrer a chave primária e filtrar, ignorando o índice.
    @Query("select b from Book b join fetch b.author "
            + "where b.title like concat(:prefix, '%') order by b.title")
    List<Book> findByTitlePrefix(@Param("prefix") String prefix, Pageable pageable);
}
