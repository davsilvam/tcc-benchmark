-- Carga semente determinística — 1.000 autores e 200.000 livros.
-- Nenhuma fonte de aleatoriedade: reexecuções produzem exatamente o mesmo conjunto.

TRUNCATE TABLE books, authors RESTART IDENTITY CASCADE;

INSERT INTO authors (id, name, nationality, birth_year)
SELECT i,
       'Autor ' || lpad(i::text, 4, '0'),
       (ARRAY['Brasileira','Portuguesa','Argentina','Chilena','Mexicana',
              'Angolana','Mocambicana','Colombiana','Peruana','Uruguaia'])[1 + (i % 10)],
       1900 + (i % 90)
FROM generate_series(1, 1000) AS s(i);

INSERT INTO books (author_id, title, isbn, publication_year, price)
SELECT 1 + (i % 1000),
       (ARRAY['Alfa','Bravo','Charlie','Delta','Echo','Foxtrot','Golf','Hotel',
              'India','Juliett','Kilo','Lima','Mike','November','Oscar','Papa',
              'Quebec','Romeo','Sierra','Tango','Uniform','Victor','Whiskey',
              'Xray','Yankee','Zulu','Ancora','Boreal','Cristal','Dunas',
              'Enigma','Farol','Granito','Horizonte','Inverno','Jangada',
              'Labirinto','Miragem','Nevoa','Oceano','Pantano','Quimera',
              'Recife','Solstice','Trovoada','Urutau','Vertigem','Wanderer',
              'Xisto','Zenite'])[1 + (i % 50)]
         || ' ' || substr(md5(i::text), 1, 12),
       lpad(i::text, 13, '0'),
       1450 + (i % 576),
       round((10 + (i % 19000) / 100.0)::numeric, 2)
FROM generate_series(1, 200000) AS s(i);

ANALYZE authors;
ANALYZE books;
