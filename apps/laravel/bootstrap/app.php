<?php

use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Http\Request;
use Illuminate\Validation\ValidationException;
use Symfony\Component\HttpKernel\Exception\HttpExceptionInterface;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        api: __DIR__.'/../routes/api.php',
        apiPrefix: 'api',
        web: __DIR__.'/../routes/web.php',
        commands: __DIR__.'/../routes/console.php',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        //
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        $exceptions->shouldRenderJsonWhen(
            fn (Request $request) => $request->is('api/*') || $request->expectsJson(),
        );

        // Corpo de erro único às cinco implementações (seção 5.2). O Laravel devolveria 422
        // com {message, errors} na falha de validação; o contrato exige 400 com
        // {status, message, violations}.
        $exceptions->render(function (ValidationException $exception, Request $request) {
            if (! $request->is('api/*')) {
                return null;
            }

            $violations = [];
            foreach ($exception->errors() as $field => $messages) {
                $violations[] = ['field' => $field, 'message' => $messages[0]];
            }

            return response()->json([
                'status' => 400,
                'message' => 'Validation failed',
                'violations' => $violations,
            ], 400);
        });

        $exceptions->render(function (HttpExceptionInterface $exception, Request $request) {
            if (! $request->is('api/*')) {
                return null;
            }

            $status = $exception->getStatusCode();

            return response()->json([
                'status' => $status,
                'message' => $exception->getMessage() !== '' ? $exception->getMessage() : 'Request failed',
            ], $status);
        });
    })->create();
