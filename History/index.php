<?php
header('Content-Type: text/plain; charset=utf-8');

foreach (glob('*.json') as $tiedosto) {
    echo $tiedosto . PHP_EOL;
}
?>
