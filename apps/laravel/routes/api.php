<?php

use App\Http\Controllers\BookController;
use Illuminate\Support\Facades\Route;

// books/search precede books/{id}: o roteador do Laravel resolve na ordem de registro.
Route::get('health', [BookController::class, 'health']);
Route::get('books', [BookController::class, 'index']);
Route::get('books/search', [BookController::class, 'search']);
Route::get('books/{id}', [BookController::class, 'show']);
Route::post('books', [BookController::class, 'store']);
Route::put('books/{id}', [BookController::class, 'update']);
