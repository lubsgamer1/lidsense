<?php
require __DIR__ . '/api/lib.php';
start_session();
$_SESSION = [];
session_destroy();
header('Location: login.php');
