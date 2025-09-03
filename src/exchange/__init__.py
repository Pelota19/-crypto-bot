# Exchaclass BinanceClient:
    def __init__(self, api_key: str = API_KEY, api_secret: str = API_SECRET, use_testnet: bool = USE_TESTNET, dry_run: bool = DRY_RUN):
        self.dry_run = dry_run
        opts = {'defaultType': 'future'}
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': opts,
        })

        if use_testnet:
            # Testnet oficial Binance Futures
            self.exchange.options['defaultType'] = 'future'
            self.exchange.urls['api'] = {
                'public': 'https://testnet.binancefuture.com/fapi/v1',
                'private': 'https://testnet.binancefuture.com/fapi/v1'
            }
            logger.info("Binance testnet mode enabled")nge module
