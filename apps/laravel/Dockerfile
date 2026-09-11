FROM php:8.5-fpm
# O OPcache NÃO entra em docker-php-ext-install: a imagem php:8.5 já o traz compilado
# estaticamente (aparece em `php -m` como Zend OPcache), e tentar instalá-lo falharia com
# "cp: cannot stat 'modules/*'". A configuração permanece em docker/php.ini.

RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends nginx libpq-dev unzip git \
 && docker-php-ext-install -j"$(nproc)" pdo_pgsql \
 && rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

WORKDIR /app

COPY composer.json composer.lock ./
RUN COMPOSER_ALLOW_SUPERUSER=1 composer install \
      --no-dev --no-scripts --no-autoloader --prefer-dist --no-interaction

COPY . .
RUN COMPOSER_ALLOW_SUPERUSER=1 composer dump-autoload --optimize --no-dev \
 && php artisan package:discover --ansi

COPY docker/nginx.conf /etc/nginx/sites-available/default
COPY docker/php-fpm.conf /usr/local/etc/php-fpm.d/zz-bench.conf
COPY docker/php.ini /usr/local/etc/php/conf.d/zz-bench.ini
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
 && chown -R www-data:www-data /app/storage /app/bootstrap/cache

EXPOSE 8080
CMD ["/entrypoint.sh"]
