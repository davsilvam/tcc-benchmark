<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Book extends Model
{
    protected $table = 'books';

    // created_at é preenchido pela aplicação, como nas demais implementações; updated_at
    // não existe no esquema (seção 2.2).
    public $timestamps = false;

    protected $fillable = [
        'author_id', 'title', 'isbn', 'publication_year', 'price', 'created_at',
    ];

    protected $casts = [
        'id' => 'integer',
        'author_id' => 'integer',
        'publication_year' => 'integer',
        // 'float' e não 'decimal:2': o cast decimal devolve string, e o contrato exige
        // número JSON em price (seção 3). O driver PDO do PostgreSQL entrega NUMERIC
        // como string.
        'price' => 'float',
        'created_at' => 'datetime',
    ];

    public function author(): BelongsTo
    {
        return $this->belongsTo(Author::class);
    }
}
