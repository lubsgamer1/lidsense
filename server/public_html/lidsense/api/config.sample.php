<?php
// Copy this file to config.php (same folder) and fill it in.
// config.php is blocked from web access by .htaccess. Never commit it to GitHub.
return [
    // phpMyAdmin / hPanel -> Databases shows these values.
    // On the same hosting account the host is normally 'localhost'.
    'db_host' => 'localhost',
    'db_name' => 'u000000000_lidsense',
    'db_user' => 'u000000000_lidsense',
    'db_pass' => 'CHANGE-ME',

    // Dashboard logins: username => password hash. Create hashes with setup.php.
    'users' => [
        // 'admin' => '$2y$10$...',
    ],

    // One-time setup page (setup.php). Set a long random string while setting up,
    // then set it back to '' (or delete setup.php) when you are done.
    'setup_token' => '',

    // A device counts as online if it has sent a heartbeat within this many seconds.
    'online_after_s' => 30,

    // Must match the Pi config (used for the threshold lines on the charts).
    'bands' => [
        ['label' => 'Hyperhydrated', 'below_s11_db' => -22],
        ['label' => 'Euhydrated',    'below_s11_db' => -15],
        ['label' => 'Hypohydrated'],
    ],
    'alert_delta_db' => 3.0,
];
