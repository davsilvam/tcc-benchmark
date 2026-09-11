import {
  BadRequestException,
  Body,
  ConflictException,
  Controller,
  DefaultValuePipe,
  Get,
  NotFoundException,
  Param,
  ParseIntPipe,
  Post,
  Put,
  Query,
  Res,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import type { Response } from 'express';
import { Repository } from 'typeorm';

import { CreateBookDto, UpdateBookDto } from './book.dto.js';
import { Author, Book, bookResponse } from './book.entity.js';

const MAX_PAGE_SIZE = 100;
const MAX_TITLE_LENGTH = 200;

function invalid(field: string) {
  return new BadRequestException({
    message: 'Validation failed',
    violations: [{ field, message: 'invalid value' }],
  });
}

function isUniqueViolation(error: unknown) {
  const candidate = error as { code?: string; driverError?: { code?: string } };
  return candidate.code === '23505' || candidate.driverError?.code === '23505';
}

@Controller('api')
export class BooksController {
  constructor(
    @InjectRepository(Book) private readonly books: Repository<Book>,
    @InjectRepository(Author) private readonly authors: Repository<Author>,
  ) {}

  @Get('health')
  health() {
    return { status: 'UP' };
  }

  @Get('books')
  async list(
    @Query('page', new DefaultValuePipe(0), ParseIntPipe) page: number,
    @Query('size', new DefaultValuePipe(20), ParseIntPipe) size: number,
  ) {
    if (page < 0) throw invalid('page');
    if (size < 1 || size > MAX_PAGE_SIZE) throw invalid('size');

    // innerJoinAndSelect mantém a listagem em UMA instrução SQL; sem ele o carregamento
    // da associação traria uma consulta por item (problema N+1), violando o critério 8.2.
    // limit/offset — e não take/skip: com junções, take/skip levam o TypeORM a emitir uma
    // consulta adicional de identificadores distintos, o que quebraria a mesma contagem.
    const rows = await this.books
      .createQueryBuilder('b')
      .innerJoinAndSelect('b.author', 'a')
      .orderBy('b.id', 'ASC')
      .limit(size)
      .offset(page * size)
      .getMany();

    return { page, size, content: rows.map(bookResponse) };
  }

  // Declarado antes de books/:id — o Nest resolve as rotas na ordem de declaração.
  @Get('books/search')
  async search(
    @Query('title') title: string | undefined,
    @Query('size', new DefaultValuePipe(20), ParseIntPipe) size: number,
  ) {
    if (!title || !title.trim() || title.length > MAX_TITLE_LENGTH) throw invalid('title');
    if (size < 1 || size > MAX_PAGE_SIZE) throw invalid('size');

    // LIKE simples, sensível a maiúsculas: ILIKE ou UPPER(...) descartariam o índice
    // idx_books_title. A ordenação por title mantém filtro e ordenação na mesma varredura
    // de intervalo, sob COLLATE "C" (seção 4.3).
    const rows = await this.books
      .createQueryBuilder('b')
      .innerJoinAndSelect('b.author', 'a')
      .where('b.title LIKE :prefix', { prefix: `${title}%` })
      .orderBy('b.title', 'ASC')
      .limit(size)
      .getMany();

    return { size, content: rows.map(bookResponse) };
  }

  @Get('books/:id')
  async byId(@Param('id', ParseIntPipe) id: number) {
    const book = await this.findWithAuthor(id);
    if (!book) throw new NotFoundException('Resource not found');
    return bookResponse(book);
  }

  @Post('books')
  async create(
    @Body() dto: CreateBookDto,
    @Res({ passthrough: true }) response: Response,
  ) {
    // Existência do autor verificada explicitamente (1 SELECT), e não delegada a violação
    // de chave estrangeira: o tratamento de erro de integridade difere entre os ORMs e
    // produziria caminhos de execução distintos entre as implementações.
    const author = await this.authors.findOne({ where: { id: dto.authorId } });
    if (!author) {
      throw new BadRequestException({
        message: 'Validation failed',
        violations: [{ field: 'authorId', message: 'author does not exist' }],
      });
    }

    const book = this.books.create({
      author,
      title: dto.title,
      isbn: dto.isbn,
      publicationYear: dto.publicationYear,
      price: dto.price,
      createdAt: new Date(),
    });

    try {
      const result = await this.books.insert(book);
      book.id = Number(result.identifiers[0].id);
    } catch (error) {
      if (isUniqueViolation(error)) throw new ConflictException('isbn already exists');
      throw error;
    }

    response.setHeader('Location', `/api/books/${book.id}`);
    return bookResponse(book);
  }

  @Put('books/:id')
  async update(@Param('id', ParseIntPipe) id: number, @Body() dto: UpdateBookDto) {
    const book = await this.findWithAuthor(id);
    if (!book) throw new NotFoundException('Resource not found');

    await this.books.update(id, {
      title: dto.title,
      publicationYear: dto.publicationYear,
      price: dto.price,
    });

    book.title = dto.title;
    book.publicationYear = dto.publicationYear;
    book.price = dto.price;
    return bookResponse(book);
  }

  private findWithAuthor(id: number) {
    return this.books
      .createQueryBuilder('b')
      .innerJoinAndSelect('b.author', 'a')
      .where('b.id = :id', { id })
      .getOne();
  }
}
