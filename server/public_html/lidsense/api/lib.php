<?php
declare(strict_types=1);

function cfg(): array {
    static $c = null;
    if ($c === null) {
        $f = __DIR__ . '/config.php';
        if (!is_file($f)) { json_out(['error' => 'api/config.php missing - copy config.sample.php'], 500); }
        $c = require $f;
    }
    return $c;
}

function db(): PDO {
    static $pdo = null;
    if ($pdo === null) {
        $c = cfg();
        $pdo = new PDO("mysql:host={$c['db_host']};dbname={$c['db_name']};charset=utf8mb4",
            $c['db_user'], $c['db_pass'], [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                PDO::ATTR_EMULATE_PREPARES => false,
            ]);
        $pdo->exec("SET time_zone = '+00:00'");
    }
    return $pdo;
}

function json_out($data, int $code = 200): void {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($data, JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION);
    exit;
}

function start_session(): void {
    if (session_status() !== PHP_SESSION_ACTIVE) {
        session_set_cookie_params(['httponly' => true, 'samesite' => 'Lax',
            'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off']);
        session_name('lidsense');
        session_start();
    }
}

function require_login(): string {
    start_session();
    if (empty($_SESSION['user'])) { json_out(['error' => 'login required'], 401); }
    $user = (string)$_SESSION['user'];
    session_write_close();   // don't block parallel API calls
    return $user;
}

/** '2026-11-23T10:00:00.123Z' -> '2026-11-23 10:00:00.123' (UTC) */
function to_mysql_time(?string $iso): ?string {
    if (!$iso) return null;
    try {
        $d = new DateTimeImmutable($iso);
        return $d->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s.v');
    } catch (Exception $e) { return null; }
}

/** MySQL DATETIME(3) (UTC) -> ISO 8601 with Z */
function iso(?string $t): ?string {
    return $t === null ? null : str_replace(' ', 'T', $t) . 'Z';
}

function num_or_null($v): ?float {
    return (is_numeric($v) && is_finite((float)$v)) ? (float)$v : null;
}

function str_or($v, string $default = '', int $max = 64): string {
    return is_string($v) ? mb_substr($v, 0, $max) : $default;
}

const RANGE_HOURS = ['1h' => 1, '6h' => 6, '24h' => 24, '7d' => 168, '30d' => 720];

function device_param(): string {
    $d = $_GET['device'] ?? '';
    if ($d === '') {
        $d = (string)db()->query('SELECT device_id FROM devices ORDER BY last_seen DESC LIMIT 1')->fetchColumn();
    }
    return $d;
}

function cast_reading(array $r): array {
    foreach (['measured_at', 'received_at'] as $k) { if (array_key_exists($k, $r)) $r[$k] = iso($r[$k]); }
    foreach (['resonant_freq_hz','s11_db','return_loss_db','bandwidth_hz','q_factor','rl_spread_db',
              'contact_rms_db','baseline_rl_db','delta_db'] as $k) {
        if (array_key_exists($k, $r) && $r[$k] !== null) $r[$k] = (float)$r[$k];
    }
    if (isset($r['seq'])) $r['seq'] = (int)$r['seq'];
    return $r;
}
