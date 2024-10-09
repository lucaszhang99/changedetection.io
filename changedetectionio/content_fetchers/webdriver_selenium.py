import os
import time

from loguru import logger
from changedetectionio.content_fetchers.base import Fetcher
import random
class fetcher(Fetcher):
    if os.getenv("WEBDRIVER_URL"):
        fetcher_description = "WebDriver Chrome/Javascript via '{}'".format(os.getenv("WEBDRIVER_URL"))
    else:
        fetcher_description = "WebDriver Chrome/Javascript"

    # Configs for Proxy setup
    # In the ENV vars, is prefixed with "webdriver_", so it is for example "webdriver_sslProxy"
    selenium_proxy_settings_mappings = ['proxyType', 'ftpProxy', 'httpProxy', 'noProxy',
                                        'proxyAutoconfigUrl', 'sslProxy', 'autodetect',
                                        'socksProxy', 'socksVersion', 'socksUsername', 'socksPassword']
    proxy = None

    def __init__(self, proxy_override=None, custom_browser_connection_url=None):
        super().__init__()
        from selenium.webdriver.common.proxy import Proxy as SeleniumProxy

        # .strip('"') is going to save someone a lot of time when they accidently wrap the env value
        if not custom_browser_connection_url:
            self.browser_connection_url = os.getenv("WEBDRIVER_URL", 'http://browser-chrome:4444/wd/hub').strip('"')
        else:
            self.browser_connection_is_custom = True
            self.browser_connection_url = custom_browser_connection_url

        # If any proxy settings are enabled, then we should setup the proxy object
        proxy_args = {}
        for k in self.selenium_proxy_settings_mappings:
            v = os.getenv('webdriver_' + k, False)
            if v:
                proxy_args[k] = v.strip('"')

        # Map back standard HTTP_ and HTTPS_PROXY to webDriver httpProxy/sslProxy
        if not proxy_args.get('webdriver_httpProxy') and self.system_http_proxy:
            proxy_args['httpProxy'] = self.system_http_proxy
        if not proxy_args.get('webdriver_sslProxy') and self.system_https_proxy:
            proxy_args['httpsProxy'] = self.system_https_proxy

        # Allows override the proxy on a per-request basis
        if proxy_override is not None:
            proxy_args['httpProxy'] = proxy_override

        if proxy_args:
            self.proxy = SeleniumProxy(raw=proxy_args)



    def run(self,
            url,
            timeout,
            request_headers,
            request_body,
            request_method,
            ignore_status_codes=False,
            current_include_filters=None,
            is_binary=False,
            empty_pages_are_a_change=False):
        import undetected_chromedriver as uc
        from undetected_chromedriver.options import ChromeOptions
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException

        class RemoteService:
            SELENOID_HOST = 'your-selenoid-host'
            service_url = 'http://browser-chrome:4444/wd/hub' # todo: dynamic passin value
            path = '/usr/bin/true'  # some existing fake path

            def start(self):
                pass

            def stop(self): # todo fix stopping
                pass

        class UdChrome(uc.Chrome):
            def __init__(self):
                options = uc.ChromeOptions()
                options = ChromeOptions()
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
                options.add_argument("--disable-blink-features=AutomationControlled")
                options._session = self
                super(uc.Chrome, self).__init__(options=options, service=RemoteService(), keep_alive=True)
                self._delay = 3
                self.options = options

        self.driver = UdChrome()
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        try:
            self.driver.get(url)
            self.driver.refresh()
        except WebDriverException as e:
            self.quit()
            raise

        # List of common resolutions
        common_resolutions = [(1280, 1024), (1366, 768), (1920, 1080), (1600, 900), (1440, 900)]
        random_resolution = random.choice(common_resolutions)
        self.driver.set_window_size(*random_resolution)

        self.driver.implicitly_wait(int(os.getenv("WEBDRIVER_DELAY_BEFORE_CONTENT_READY", 5)))

        if self.webdriver_js_execute_code is not None:
            self.driver.execute_script(self.webdriver_js_execute_code)
            self.driver.implicitly_wait(int(os.getenv("WEBDRIVER_DELAY_BEFORE_CONTENT_READY", 5)))

        self.status_code = 200
        time.sleep(int(os.getenv("WEBDRIVER_DELAY_BEFORE_CONTENT_READY", 5)) + self.render_extract_delay)
        self.content = self.driver.page_source
        self.headers = {}
        self.screenshot = self.driver.get_screenshot_as_png()

    # Does the connection to the webdriver work? run a test connection.
    def is_ready(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions

        self.driver = webdriver.Remote(
            command_executor=self.command_executor,
            options=ChromeOptions())

        # driver.quit() seems to cause better exceptions
        self.quit()
        return True

    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.debug(f"Content Fetcher > Exception in chrome shutdown/quit {str(e)}")