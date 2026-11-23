<?php
// One-time setup helper. Enable by putting a long random 'setup_token' in api/config.php,
// open setup.php?token=THAT-TOKEN, then clear the token (or delete this file) afterwards.
declare(strict_types=1);
require __DIR__ . '/api/lib.php';
$c = cfg();
$token = (string)($_REQUEST['token'] ?? '');
if (($c['setup_token'] ?? '') === '' || !hash_equals((string)$c['setup_token'], $token)) {
    http_response_code(403); exit('Setup is disabled. Set setup_token in api/config.php and open setup.php?token=...');
}
$msg = []; $h = fn($s) => htmlspecialchars((string)$s);
try {
    $pdo = db();
    $tables = $pdo->query("SHOW TABLES")->fetchAll(PDO::FETCH_COLUMN);
    $msg[] = 'Database connection OK.';
    if (($_POST['action'] ?? '') === 'schema') {
        $sqlText = preg_replace('/^\s*--.*$/m', '', file_get_contents(__DIR__ . '/api/schema.sql') ?: '');
        foreach (array_filter(array_map('trim', explode(";\n", $sqlText))) as $sql) { $pdo->exec($sql); }
        $tables = $pdo->query("SHOW TABLES")->fetchAll(PDO::FETCH_COLUMN);
        $msg[] = 'Schema created.';
    }
    if (($_POST['action'] ?? '') === 'device') {
        $id = preg_replace('/[^A-Za-z0-9_-]/', '', (string)$_POST['device_id']);
        $key = bin2hex(random_bytes(32));
        $pdo->prepare('INSERT INTO devices (device_id, name, api_key_hash) VALUES (?,?,?)
                       ON DUPLICATE KEY UPDATE name = VALUES(name), api_key_hash = VALUES(api_key_hash)')
            ->execute([$id, (string)$_POST['name'], hash('sha256', $key)]);
        $msg[] = "Device <b>{$h($id)}</b> saved. Put this line in /etc/lidsense/secrets.env on the Pi (shown only once):"
               . "<pre>LIDSENSE_API_KEY={$h($key)}</pre>";
    }
} catch (Throwable $e) { $msg[] = 'Database error: ' . $h($e->getMessage()); $tables = []; }
if (($_POST['action'] ?? '') === 'hash') {
    $msg[] = "Add this line to the 'users' array in api/config.php:<pre>'" . $h($_POST['user'])
           . "' => '" . $h(password_hash((string)$_POST['password'], PASSWORD_DEFAULT)) . "',</pre>";
}
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LidSense setup</title><link rel="stylesheet" href="assets/style.css"></head><body class="setup-page"><main class="setup">
<h1>LidSense setup</h1>
<?php foreach ($msg as $m) echo "<div class='note'>$m</div>"; ?>
<p class="muted">Tables: <?= $h(implode(', ', $tables) ?: 'none') ?></p>
<form method="post"><input type="hidden" name="token" value="<?= $h($token) ?>"><input type="hidden" name="action" value="schema">
<h2>1. Create tables</h2><p class="muted">Or import sql/schema.sql in phpMyAdmin.</p><button class="btn">Create tables</button></form>
<form method="post"><input type="hidden" name="token" value="<?= $h($token) ?>"><input type="hidden" name="action" value="device">
<h2>2. Register a Raspberry Pi</h2><label>Device ID (as in config.yaml)<input name="device_id" value="lidsense-01" required></label>
<label>Name<input name="name" value="LidSense prototype 1"></label><button class="btn">Create device and key</button></form>
<form method="post"><input type="hidden" name="token" value="<?= $h($token) ?>"><input type="hidden" name="action" value="hash">
<h2>3. Create a dashboard login</h2><label>Username<input name="user" required></label>
<label>Password<input name="password" type="password" minlength="10" required></label><button class="btn">Make password hash</button></form>
<p><b>When finished:</b> set <code>'setup_token' => ''</code> in api/config.php.</p>
</main></body></html>
