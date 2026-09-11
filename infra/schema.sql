-- Esquema da API de referência — TCC
-- Criado por SQL puro, nunca por migrations de ORM (ver seção 2.4 da especificação).

DROP TABLE IF EXISTS books;
DROP TABLE IF EXISTS authors;

CREATE TABLE authors (
    id          BIGINT       PRIMARY KEY,
    name        VARCHAR(120) NOT NULL,
    nationality VARCHAR(60)  NOT NULL,
    birth_year  INTEGER      NOT NULL
);

CREATE TABLE books (
    id               BIGSERIAL     PRIMARY KEY,
    author_id        BIGINT        NOT NULL REFERENCES authors (id),
    -- COLLATE "C" e requisito, não detalhe: com o agrupamento padrão do banco, um índice
    -- btree comum não atende a `LIKE 'prefixo%'`. Sob COLLATE "C" o mesmo índice serve ao
    -- filtro por prefixo E a ordenação, em varredura de intervalo única (ver seção 4.3).
    title            VARCHAR(200)  COLLATE "C" NOT NULL,
    isbn             CHAR(13)      NOT NULL UNIQUE,
    publication_year INTEGER       NOT NULL,
    price            NUMERIC(10,2) NOT NULL,
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_books_author_id ON books (author_id);
CREATE INDEX idx_books_title     ON books (title);
