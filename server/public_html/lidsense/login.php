<?php
declare(strict_types=1);
require __DIR__ . '/api/lib.php';
start_session();
$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $u = (string)($_POST['user'] ?? '');
    $p = (string)($_POST['password'] ?? '');
    $hash = cfg()['users'][$u] ?? null;
    usleep(300000);   // slow down password guessing
    if ($hash && password_verify($p, $hash)) {
        session_regenerate_id(true);
        $_SESSION['user'] = $u;
        header('Location: ./');
        exit;
    }
    $error = 'Wrong username or password.';
}
?><!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LidSense sign in</title><link rel="stylesheet" href="assets/style.css"></head>
<body class="login-page">
<form class="login-card" method="post" autocomplete="on">
  <div class="brand"><span class="brand-mark" aria-hidden="true"></span>LidSense</div>
  <h1>Sign in</h1>
  <p class="muted">Hydration monitor dashboard</p>
  <?php if ($error): ?><p class="form-error" role="alert"><?= htmlspecialchars($error) ?></p><?php endif; ?>
  <label>Username<input name="user" required autocomplete="username"></label>
  <label>Password<input name="password" type="password" required autocomplete="current-password"></label>
  <button class="btn primary" type="submit">Sign in</button>
</form>
</body></html>
