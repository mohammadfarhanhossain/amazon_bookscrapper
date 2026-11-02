INSERT INTO sources (code, name, base_url, currency, is_active)
VALUES ('amazon', 'Amazon Books', 'https://www.amazon.com', 'USD', 1)
ON DUPLICATE KEY UPDATE name = VALUES(name), base_url = VALUES(base_url), currency = VALUES(currency);
