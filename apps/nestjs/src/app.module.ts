import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { Author, Book } from './books/book.entity.js';
import { BooksController } from './books/books.controller.js';

@Module({
  imports: [
    TypeOrmModule.forRoot({
      type: 'postgres',
      host: process.env.DB_HOST ?? 'localhost',
      port: Number(process.env.DB_PORT ?? '5432'),
      username: process.env.DB_USER ?? 'bench',
      password: process.env.DB_PASSWORD ?? 'bench',
      database: process.env.DB_NAME ?? 'tccbench',
      entities: [Author, Book],
      synchronize: false, // esquema criado por SQL puro (secao 2.4)
      logging: false, // sem log de consultas (secao 6.1)
      cache: false, // cache de segundo nivel desabilitado (secao 6.1)
      extra: { min: 10, max: 10 }, // pool fixo em 10 conexoes (secao 6.1)
    }),
    TypeOrmModule.forFeature([Author, Book]),
  ],
  controllers: [BooksController],
})
export class AppModule {}
