import { ArgumentsHost, Catch, ExceptionFilter, HttpException } from '@nestjs/common';
import type { Response } from 'express';

// Corpo de erro único às cinco implementações (seção 5.2), no lugar do formato padrão do
// Nest ({ statusCode, message, error }). O campo violations é omitido quando ausente.
@Catch(HttpException)
export class ApiErrorFilter implements ExceptionFilter {
  catch(exception: HttpException, host: ArgumentsHost) {
    const response = host.switchToHttp().getResponse<Response>();
    const status = exception.getStatus();
    const payload = exception.getResponse();
    const detail = typeof payload === 'string' ? {} : (payload as Record<string, unknown>);

    const body: Record<string, unknown> = {
      status,
      message: typeof detail.message === 'string' ? detail.message : exception.message,
    };
    if (Array.isArray(detail.violations)) {
      body.violations = detail.violations;
    }

    response.status(status).json(body);
  }
}
