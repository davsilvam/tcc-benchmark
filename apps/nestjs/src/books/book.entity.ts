import {
  Column,
  Entity,
  JoinColumn,
  ManyToOne,
  PrimaryColumn,
  PrimaryGeneratedColumn,
} from 'typeorm';

// O esquema é externo (seção 2.4): synchronize permanece falso e nenhuma migration é
// gerada. As entidades apenas mapeiam uma estrutura pré-existente.

@Entity('authors')
export class Author {
  // authors.id não é serial: os identificadores vêm da carga semente.
  @PrimaryColumn({ type: 'bigint' })
  id!: number;

  @Column({ type: 'varchar', length: 120 })
  name!: string;

  @Column({ type: 'varchar', length: 60 })
  nationality!: string;

  @Column({ name: 'birth_year', type: 'int' })
  birthYear!: number;
}

@Entity('books')
export class Book {
  @PrimaryGeneratedColumn({ type: 'bigint' })
  id!: number;

  @ManyToOne(() => Author, { nullable: false })
  @JoinColumn({ name: 'author_id' })
  author!: Author;

  @Column({ type: 'varchar', length: 200 })
  title!: string;

  @Column({ type: 'char', length: 13 })
  isbn!: string;

  @Column({ name: 'publication_year', type: 'int' })
  publicationYear!: number;

  @Column({ type: 'numeric', precision: 10, scale: 2 })
  price!: number;

  @Column({ name: 'created_at', type: 'timestamptz' })
  createdAt!: Date;
}

export function bookResponse(book: Book) {
  return {
    id: book.id,
    title: book.title,
    isbn: book.isbn,
    publicationYear: book.publicationYear,
    price: book.price,
    createdAt: book.createdAt.toISOString(),
    author: {
      id: book.author.id,
      name: book.author.name,
      nationality: book.author.nationality,
      birthYear: book.author.birthYear,
    },
  };
}
