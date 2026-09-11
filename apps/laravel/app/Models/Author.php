<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Author extends Model
{
    protected $table = 'authors';

    // O esquema é externo (seção 2.4): nenhuma migration é gerada ou executada, e as
    // colunas created_at/updated_at do Eloquent não existem nesta tabela.
    public $timestamps = false;

    protected $casts = [
        'id' => 'integer',
        'birth_year' => 'integer',
    ];
}
