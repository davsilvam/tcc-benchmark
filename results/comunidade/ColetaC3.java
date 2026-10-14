import java.io.PrintWriter;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Coleta do indicador C3 (pull requests fechados nos ultimos 12 meses) com os filtros da secao 3.3:
 *  - ao menos uma revisao (qualificador -review:none da Search API);
 *  - intervalo entre abertura e fechamento de pelo menos 1 hora (Alves Junior et al., 2022);
 *  - autor que nao seja conta automatizada (user.type = Bot).
 *
 * Usa apenas a API REST (Search API). Janela fixa: 10/09/2025 12:01 UTC a 10/09/2026 12:01 UTC
 * (instante da coleta de estrelas e forks, 10/09/2026 09:01 UTC-3), o que torna a coleta reproduzivel.
 *
 * Execucao (Java 17+): defina GITHUB_TOKEN (somente leitura, repositorios publicos) e rode
 *   java ColetaC3.java
 * Saidas: tabela no console e o arquivo c3_prs.csv (um PR por linha, para auditoria).
 */
public class ColetaC3 {

    static final Instant INICIO = Instant.parse("2025-09-10T12:01:00Z");
    static final Instant FIM = Instant.parse("2026-09-10T12:01:00Z");
    static final Duration INTERVALO_MIN = Duration.ofHours(1);
    static final long PAUSA_MS = 2200; // Search API: 30 requisicoes por minuto

    // nome, repositorio, valor bruto da planilha (state:closed, sem filtros, sem limite superior)
    static final String[][] REPOS = {
        {"Spring Boot", "spring-projects/spring-boot", "671"},
        {"Django", "django/django", "1909"},
        {"NestJS", "nestjs/nest", "1794"},
        {"Laravel", "laravel/framework", "3610"},
        {"ASP.NET Core", "dotnet/aspnetcore", "2677"},
    };

    record Pr(Instant criado, Instant fechado, boolean integrado, boolean bot) {
        boolean intervaloOk() {
            return Duration.between(criado, fechado).compareTo(INTERVALO_MIN) >= 0;
        }
    }

    static final HttpClient HTTP = HttpClient.newHttpClient();
    static String token;

    public static void main(String[] args) throws Exception {
        token = System.getenv("GITHUB_TOKEN");
        if (token == null || token.isBlank()) {
            System.err.println("Defina a variavel de ambiente GITHUB_TOKEN.");
            System.exit(1);
        }
        System.out.printf("Janela: %s a %s (UTC)%n%n", INICIO, FIM);
        System.out.printf("%-13s %8s %7s %6s %9s %9s %9s %9s%n",
            "Framework", "Planilha", "Bruto", "Bots", "Sem bot", "+ >=1h", "C3 base", "C3 merged");
        try (PrintWriter csv = new PrintWriter("c3_prs.csv", StandardCharsets.UTF_8)) {
            csv.println("framework,numero,criado,fechado,integrado,bot,com_revisao");
            for (String[] r : REPOS) {
                Map<Integer, Pr> todos = new LinkedHashMap<>();
                Set<Integer> revisados = new HashSet<>();
                coletar(r[1], INICIO, FIM, false, todos, revisados);
                coletar(r[1], INICIO, FIM, true, todos, revisados);
                long bruto = todos.size();
                long bots = todos.values().stream().filter(Pr::bot).count();
                long semBot = bruto - bots;
                long comIntervalo = todos.values().stream().filter(p -> !p.bot() && p.intervaloOk()).count();
                long base = todos.entrySet().stream()
                    .filter(e -> !e.getValue().bot() && e.getValue().intervaloOk() && revisados.contains(e.getKey()))
                    .count();
                long baseMerged = todos.entrySet().stream()
                    .filter(e -> !e.getValue().bot() && e.getValue().intervaloOk() && revisados.contains(e.getKey())
                        && e.getValue().integrado())
                    .count();
                System.out.printf("%-13s %8s %7d %6d %9d %9d %9d %9d%n",
                    r[0], r[2], bruto, bots, semBot, comIntervalo, base, baseMerged);
                for (Map.Entry<Integer, Pr> e : todos.entrySet()) {
                    Pr p = e.getValue();
                    csv.printf("%s,%d,%s,%s,%b,%b,%b%n", r[0], e.getKey(), p.criado(), p.fechado(),
                        p.integrado(), p.bot(), revisados.contains(e.getKey()));
                }
                csv.flush();
            }
        }
        System.out.println();
        System.out.println("Bruto: fechados na janela. Sem bot: exclui autores do tipo Bot.");
        System.out.println("+ >=1h: sem bot e com intervalo minimo de 1h (variante sem exigencia de revisao).");
        System.out.println("C3 base: sem bot, >=1h e ao menos uma revisao (valor do cenario base).");
        System.out.println("C3 merged: C3 base restrito a PRs integrados (variante da analise de sensibilidade).");
    }

    /**
     * Coleta uma faixa de tempo. Se a faixa tem 1000 ou mais resultados (limite da Search API),
     * divide ao meio recursivamente. Com soRevisados, apenas registra os numeros de PRs com revisao.
     */
    static void coletar(String repo, Instant a, Instant b, boolean soRevisados,
                        Map<Integer, Pr> todos, Set<Integer> revisados) throws Exception {
        String q = "repo:" + repo + " is:pr is:closed closed:" + a + ".." + b + (soRevisados ? " -review:none" : "");
        for (int pagina = 1; ; pagina++) {
            Map<String, Object> resp = buscar(q, pagina);
            int total = ((Double) resp.get("total_count")).intValue();
            if (pagina == 1 && total >= 1000) {
                long seg = Duration.between(a, b).getSeconds();
                if (seg < 2) throw new IllegalStateException("Faixa de 1 s com 1000+ PRs: " + q);
                Instant meio = a.plusSeconds(seg / 2).truncatedTo(ChronoUnit.SECONDS);
                coletar(repo, a, meio, soRevisados, todos, revisados);
                coletar(repo, meio.plusSeconds(1), b, soRevisados, todos, revisados);
                return;
            }
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> itens = (List<Map<String, Object>>) resp.get("items");
            for (Map<String, Object> it : itens) {
                int numero = ((Double) it.get("number")).intValue();
                if (soRevisados) {
                    revisados.add(numero);
                    continue;
                }
                @SuppressWarnings("unchecked")
                Map<String, Object> user = (Map<String, Object>) it.get("user");
                @SuppressWarnings("unchecked")
                Map<String, Object> pull = (Map<String, Object>) it.get("pull_request");
                boolean bot = user != null && "Bot".equals(user.get("type"));
                boolean integrado = pull != null && pull.get("merged_at") != null;
                todos.put(numero, new Pr(Instant.parse((String) it.get("created_at")),
                    Instant.parse((String) it.get("closed_at")), integrado, bot));
            }
            if (itens.size() < 100 || pagina * 100 >= total) return;
        }
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> buscar(String q, int pagina) throws Exception {
        String url = "https://api.github.com/search/issues?per_page=100&page=" + pagina
            + "&q=" + URLEncoder.encode(q, StandardCharsets.UTF_8);
        HttpRequest req = HttpRequest.newBuilder(URI.create(url))
            .header("Authorization", "Bearer " + token)
            .header("Accept", "application/vnd.github+json")
            .header("X-GitHub-Api-Version", "2022-11-28")
            .header("User-Agent", "tcc-coleta-c3")
            .GET().build();
        for (int tentativa = 1; ; tentativa++) {
            HttpResponse<String> resp = HTTP.send(req, HttpResponse.BodyHandlers.ofString());
            int s = resp.statusCode();
            if (s == 200) {
                Thread.sleep(PAUSA_MS);
                return (Map<String, Object>) Json.parse(resp.body());
            }
            if ((s == 403 || s == 429) && tentativa < 8) {
                long espera = resp.headers().firstValue("Retry-After").map(Long::parseLong).orElse(65L);
                System.err.printf("HTTP %d; aguardando %d s (tentativa %d)%n", s, espera, tentativa);
                Thread.sleep(espera * 1000);
                continue;
            }
            throw new IllegalStateException("HTTP " + s + ": " + resp.body());
        }
    }

    /** Leitor JSON minimo (objetos, listas, textos, numeros, booleanos e nulo). */
    static final class Json {
        final String s;
        int i = 0;

        Json(String s) { this.s = s; }

        static Object parse(String s) {
            Json j = new Json(s);
            j.ws();
            return j.valor();
        }

        void ws() {
            while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++;
        }

        Object valor() {
            switch (s.charAt(i)) {
                case '{': return objeto();
                case '[': return lista();
                case '"': return texto();
                case 't': i += 4; return Boolean.TRUE;
                case 'f': i += 5; return Boolean.FALSE;
                case 'n': i += 4; return null;
                default: return numero();
            }
        }

        Map<String, Object> objeto() {
            Map<String, Object> m = new LinkedHashMap<>();
            i++;
            ws();
            if (s.charAt(i) == '}') { i++; return m; }
            while (true) {
                ws();
                String k = texto();
                ws();
                i++; // ':'
                ws();
                m.put(k, valor());
                ws();
                if (s.charAt(i++) == '}') return m;
            }
        }

        List<Object> lista() {
            List<Object> l = new java.util.ArrayList<>();
            i++;
            ws();
            if (s.charAt(i) == ']') { i++; return l; }
            while (true) {
                ws();
                l.add(valor());
                ws();
                if (s.charAt(i++) == ']') return l;
            }
        }

        String texto() {
            i++;
            StringBuilder sb = new StringBuilder();
            while (true) {
                char c = s.charAt(i++);
                if (c == '"') return sb.toString();
                if (c != '\\') { sb.append(c); continue; }
                char e = s.charAt(i++);
                switch (e) {
                    case 'n': sb.append('\n'); break;
                    case 't': sb.append('\t'); break;
                    case 'r': sb.append('\r'); break;
                    case 'b': sb.append('\b'); break;
                    case 'f': sb.append('\f'); break;
                    case 'u': sb.append((char) Integer.parseInt(s.substring(i, i + 4), 16)); i += 4; break;
                    default: sb.append(e);
                }
            }
        }

        Double numero() {
            int ini = i;
            while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
            return Double.valueOf(s.substring(ini, i));
        }
    }
}
