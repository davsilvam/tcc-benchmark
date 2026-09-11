import { IsInt, IsNumber, IsString, Length, Matches, Max, Min } from 'class-validator';

export class CreateBookDto {
  @IsInt()
  @Min(1)
  authorId!: number;

  @IsString()
  @Length(1, 200)
  title!: string;

  @Matches(/^[0-9]{13}$/)
  isbn!: string;

  @IsInt()
  @Min(1450)
  @Max(2100)
  publicationYear!: number;

  @IsNumber({ maxDecimalPlaces: 2 })
  @Min(0)
  price!: number;
}

// authorId não é atualizável: permitir a troca de autor exigiria uma terceira consulta e o
// número de consultas passaria a depender do conteúdo da requisição (seção 4.5).
export class UpdateBookDto {
  @IsString()
  @Length(1, 200)
  title!: string;

  @IsInt()
  @Min(1450)
  @Max(2100)
  publicationYear!: number;

  @IsNumber({ maxDecimalPlaces: 2 })
  @Min(0)
  price!: number;
}
