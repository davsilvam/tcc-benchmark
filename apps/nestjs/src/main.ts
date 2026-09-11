import { BadRequestException, ValidationPipe } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import type { ValidationError } from 'class-validator';
import pg from 'pg';

import { ApiErrorFilter } from './api-error.filter.js';
import { AppModule } from './app.module.js';

// O node-postgres devolve int8 e numeric como *string*, para não perder precisão. O
// contrato exige número JSON em id e price (seção 3): os identificadores vão até 2x10^5 e
// os preços têm duas casas decimais, muito dentro do inteiro seguro do JavaScript.
pg.types.setTypeParser(20, (value: string) => Number.parseInt(value, 10)); // int8
pg.types.setTypeParser(1700, (value: string) => Number.parseFloat(value)); // numeric

async function bootstrap() {
  // Nivel de log WARN, sem log de requisições (seção 6.1).
  const app = await NestFactory.create(AppModule, { logger: ['warn', 'error'] });

  // transform NÃO é habilitado. Com transform: true o ValidationPipe global converte os
  // parametros primitivos ANTES dos pipes de parametro: `?page=abc` vira NaN, o
  // DefaultValuePipe troca NaN pelo valor padrão e a requisição inválida devolve 200 em
  // vez do 400 exigido pelo contrato (seção 4.1). Sem transform, a string chega intacta ao
  // ParseIntPipe. Os corpos JSON já chegam com os tipos corretos, e whitelist continua
  // removendo campos não declarados nos DTOs.
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      exceptionFactory: (errors: ValidationError[]) =>
        new BadRequestException({
          message: 'Validation failed',
          violations: errors.map((error) => ({
            field: error.property,
            message: Object.values(error.constraints ?? {})[0] ?? 'invalid value',
          })),
        }),
    }),
  );
  app.useGlobalFilters(new ApiErrorFilter());

  // Processo único, sem clusterização (seção 6.2).
  await app.listen(8080, '0.0.0.0');
}

await bootstrap();
