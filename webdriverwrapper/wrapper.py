# -*- coding: utf-8 -*-

from __future__ import absolute_import

import functools
import logging
logging.basicConfig(level=logging.INFO)
try:
    from urlparse import urlparse, urlunparse
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlparse, urlunparse, urlencode

try:
    input = raw_input
except NameError:
    pass

import selenium.common.exceptions as selenium_exc
from selenium.webdriver import *
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import Select, WebDriverWait

from .download import DownloadUrl, DownloadFile
from .errors import WebdriverWrapperErrorMixin
from .exceptions import _create_exception_msg, _create_exception_msg_tag
from .info import WebdriverWrapperInfoMixin
from .utils import force_text

__all__ = (
    'Firefox',
    'FirefoxProfile',
    'Chrome',
    'ChromeOptions',
    'Ie',
    'Opera',
    'PhantomJS',
    'Remote',
    'DesiredCapabilities',
    'ActionChains',
    'TouchActions',
    'Proxy',
)


class _ConvertToWebelementWrapper(object):
    def __call__(self, f):
        @functools.wraps(f)
        def wrapper(*args, **kwds):
            res = f(*args, **kwds)
            res = self._convert_result(res)
            return res
        return wrapper

    @classmethod
    def _convert_result(cls, res):
        if type(res) is WebElement:
            res = cls._convert_into_webelementwrapper(res)
        elif isinstance(res, (list, tuple)):
            for index, item in enumerate(res):
                res[index] = cls._convert_result(item)
        return res

    @classmethod
    def _convert_into_webelementwrapper(cls, webelement):
        try:
            if webelement.tag_name == 'form':
                from webdriverwrapper.forms import Form
                wrapped = Form(webelement)
            elif webelement.tag_name == 'select':
                wrapped = _SelectWrapper(webelement)
            else:
                wrapped = _WebElementWrapper(webelement)
        except selenium_exc.StaleElementReferenceException:
            return webelement
        else:
            return wrapped


class _WebdriverBaseWrapper(object):
    """
    Class wrapping both
    :py:class:`selenium.WebDriver <selenium.webdriver.remote.webdriver.WebDriver>`
    and :py:class:`selenium.WebElement <selenium.webdriver.remote.webelement.WebElement>`.
    """

    def contains_text(self, text):
        """
        Does page or element contains `text`?

        Uses method :py:meth:`~._WebdriverBaseWrapper.find_elements_by_text`.
        """
        return bool(self.find_elements_by_text(text))

    def find_element_by_text(self, text):
        """
        Returns first element on page or in element containing ``text``.

        .. versionadded:: 2.0
        """
        elms = self.find_elements_by_text(text)
        if not elms:
            raise selenium_exc.NoSuchElementException(u'No element containing text "{}" at {}.'.format(force_text(text), self.current_url))
        return elms[0]

    def find_elements_by_text(self, text):
        """
        Returns all elements on page or in element containing ``text``.

        .. versionchanged:: 2.0
            Searching in all text nodes. Before it wouldn't find string "text"
            in HTML like ``<div>some<br />text in another text node</div>``.
        """
        # XPATH have to be byte string.
        text = force_text(text).encode('utf8')
        elms = self.find_elements_by_xpath(
            './/*/text()[contains(., "{}") and not(ancestor-or-self::*[@data-selenium-not-search])]/..'.format(text)
        )
        return elms

    def click(self, *args, **kwds):
        """
        When you not pass any argument, it clicks on current element. If you
        pass some arguments, it works as following snippet. For more info what
        you can pass check out method :py:meth:`~._WebdriverBaseWrapper.get_elm`.

        .. code-block:: python

            driver.get_elm('someid').click()
        """
        if args or kwds:
            elm = self.get_elm(*args, **kwds)
            elm.click()
        else:
            super(_WebdriverBaseWrapper, self).click()

    def get_elm(
        self,
        id_=None, class_name=None, name=None, tag_name=None, xpath=None,
        parent_id=None, parent_class_name=None, parent_name=None, parent_tag_name=None,
        css_selector=None
    ):
        """
        Returns first found element. This method uses
        :py:meth:`~._WebdriverBaseWrapper.get_elms`.
        """
        elms = self.get_elms(
            id_, class_name, name, tag_name, xpath,
            parent_id, parent_class_name, parent_name, parent_tag_name,
            css_selector
        )
        if not elms:
            raise selenium_exc.NoSuchElementException(_create_exception_msg(
                id_, class_name, name, tag_name,
                parent_id, parent_class_name, parent_name, parent_tag_name,
                xpath, css_selector, self.current_url,
            ))
        return elms[0]

    def get_elms(
        self,
        id_=None, class_name=None, name=None, tag_name=None, xpath=None,
        parent_id=None, parent_class_name=None, parent_name=None, parent_tag_name=None,
        css_selector=None
    ):
        """
        Shortcut for :py:meth:`find_element* <selenium.webdriver.remote.webelement.WebElement.find_element>`
        methods. It's shorter and you can quickly find element in element.

        .. code-block:: python

            elm = driver.find_element_by_id('someid')
            elm.find_elements_by_class_name('someclasss')

            # vs.

            elm = driver.get_elm(parent_id='someid', class_name='someclass')
        """
        if parent_id or parent_class_name or parent_name or parent_tag_name:
            parent = self.get_elm(parent_id, parent_class_name, parent_name, parent_tag_name)
        else:
            parent = self

        if len([x for x in (id_, class_name, tag_name, xpath) if x is not None]) > 1:
            raise Exception('You can find element only by one param.')

        if id_ is not None:
            return parent.find_elements_by_id(id_)
        elif class_name is not None:
            return parent.find_elements_by_class_name(class_name)
        elif name is not None:
            return parent.find_elements_by_name(name)
        elif tag_name is not None:
            return parent.find_elements_by_tag_name(tag_name)
        elif xpath is not None:
            return parent.find_elements_by_xpath(xpath)
        elif css_selector is not None:
            return parent.find_elements_by_css_selector(css_selector)
        else:
            raise Exception('You must specify id or name of element on which you want to click.')

    def find_element(self, by=By.ID, value=None):
        callback = self._get_seleniums_driver_class().find_element
        return self._find_element_or_elements(callback, by, value)

    def find_elements(self, by=By.ID, value=None):
        callback = self._get_seleniums_driver_class().find_elements
        return self._find_element_or_elements(callback, by, value)

    def _get_seleniums_driver_class(self):
        next_is_selenium_driver_class = False
        driver_class = None
        for cls in self.__class__.mro():
            if next_is_selenium_driver_class:
                driver_class = cls
                break
            if cls is _WebdriverBaseWrapper:
                next_is_selenium_driver_class = True
        if not driver_class:
            raise Exception('WebDriver class not found')
        return driver_class

    #  Map from selenium's By class to name of params used in this wrapper. It's
    #+ used for making helpful messages.
    #  Commented lines are not supported.
    _by_to_string_param_map = {
        By.ID: 'id_',
        By.XPATH: 'xpath',
        #By.LINK_TEXT: 'link_text',
        #By.PARTIAL_LINK_TEXT: 'partial_link_text',
        By.NAME: 'name',
        By.TAG_NAME: 'tag_name',
        By.CLASS_NAME: 'class_name',
        #By.CSS_SELECTOR: 'css_selector',
    }

    @_ConvertToWebelementWrapper()
    def _find_element_or_elements(self, callback, by, value):
        if by in self._by_to_string_param_map:
            msg = _create_exception_msg(**{
                self._by_to_string_param_map[by]: value,
                'url': self.current_url,
            })
        else:
            msg = ''
        try:
            return callback(self, by, value)
        except (
            selenium_exc.NoSuchElementException,
            selenium_exc.StaleElementReferenceException,
            selenium_exc.InvalidElementStateException,
            selenium_exc.ElementNotVisibleException,
            selenium_exc.ElementNotSelectableException,
        ) as exc:
            raise exc.__class__(msg)


class _WebdriverWrapper(WebdriverWrapperErrorMixin, WebdriverWrapperInfoMixin, _WebdriverBaseWrapper):
    """
    Class wrapping :py:class:`selenium.WebDriver <selenium.webdriver.remote.webdriver.WebDriver>`.
    """

    def break_point(self):
        """
        Stops testing and wait for pressing enter to continue.

        Useful when you need check Chrome console for some info for example.

        .. versionadded:: 2.1
        """
        logging.info('Break point. Type enter to continue.')
        input()

    def wait_for_element(self, timeout=10, message='', *args, **kwds):
        """
        Shortcut for waiting for element. If it not ends with exception, it
        returns that element. Same as following:

        .. code-block:: python

            selenium.webdriver.support.wait.WebDriverWait(driver, timeout).until(lambda driver: driver.get_elm(...))
        """
        if not message:
            message = _create_exception_msg(*args, **kwds)
        self.wait(timeout).until(lambda driver: driver.get_elm(*args, **kwds), message=message)

        # Also return that element for which is waiting.
        elm = self.get_elm(*args, **kwds)
        return elm

    def wait_for_element_hide(self, timeout=10, message='', *args, **kwds):
        """
        Shortcut for waiting for hiding of element. Same as following:

        .. code-block:: python

            selenium.webdriver.support.wait.WebDriverWait(driver, timeout).until(lambda driver: not driver.get_elm(...))

        .. versionadded:: 2.0
        """
        if not message:
            message = 'Element {} still visible.'.format(_create_exception_msg_tag(*args, **kwds))
        self.wait(timeout).until(lambda driver: not driver.get_elms(*args, **kwds) or not driver.get_elm(*args, **kwds).is_displayed(), message=message)

    def wait(self, timeout=10):
        """
        Calls following snippet so you don't have to remember what import. See
        :py:obj:`WebDriverWait <selenium.webdriver.support.wait.WebDriverWait>` for more
        information.

        .. code-block:: python

            selenium.webdriver.support.wait.WebDriverWait(driver, timeout)

        Example:

        .. code-block:: python

            driver.wait().until(lambda driver: len(driver.find_element_by_id('elm')) > 10)

        If you need to wait for element, consider using
        :py:meth:`~._WebdriverWrapper.wait_for_element` instead.
        """
        return WebDriverWait(self, timeout)

    def go_to(self, path=None, query=None):
        """
        You have to pass absolute URL to method
        :py:meth:`~selenium.webdriver.remote.webdriver.WebDriver.get`. This
        method help you to pass only relative ``path`` and/or ``query``. See
        method :py:meth:`.get_url` for more information.

        .. versionchanged:: 2.0
            Removed parameter ``domain``. If you want to go to completely
            another web app, use absolute address.
        """
        self.get(self.get_url(path, query))

    def get_url(self, path=None, query=None):
        """
        You have to pass absolute URL to method
        :py:meth:`~selenium.webdriver.remote.webdriver.WebDriver.get`. This
        method help you to pass only relative ``path`` and/or ``query``. Scheme
        and domains is append to URL from
        :py:attr:`~selenium.webdriver.remote.webdriver.WebDriver.current_url`.

        ``query`` can be final string or dictionary. On dictionary it calls
        :py:func:`urllib.urlencode`.

        .. versionadded:: 2.0
        """
        if urlparse(path).netloc:
            return path

        if isinstance(query, dict):
            query = urlencode(query)

        url_parts = urlparse(self.current_url)
        new_url_parts = (
            url_parts.scheme,
            url_parts.netloc,
            path or url_parts.path,
            None,  # params
            query,
            None,  # fragment
        )
        url = urlunparse(new_url_parts)

        return url

    def switch_to_window(self, window_name=None, title=None, url=None):
        """
        WebDriver implements switching to other window only by it's name. With
        wrapper there is also option to switch by title of window or URL. URL
        can be also relative path.
        """
        if window_name:
            self._get_seleniums_driver_class().switch_to_window(self, window_name)
            return

        if url:
            url = self.get_url(path=url)

        for window_handle in self.window_handles:
            self._get_seleniums_driver_class().switch_to_window(self, window_handle)
            if title and self.title == title:
                return
            if url and self.current_url == url:
                return
        raise selenium_exc.NoSuchWindowException('Window (title=%s, url=%s) not found.' % (title, url))

    def close_window(self, window_name=None, title=None, url=None):
        """
        WebDriver implements only closing current window. If you want to close
        some window without having to switch to it, use this method.
        """
        main_window_handle = self.current_window_handle
        self.switch_to_window(window_name, title, url)
        self.close()
        self.switch_to_window(main_window_handle)

    def close_other_windows(self):
        """
        Closes all not current windows. Useful for tests - after each test you
        can automatically close all windows.
        """
        main_window_handle = self.current_window_handle
        for window_handle in self.window_handles:
            if window_handle == main_window_handle:
                continue
            self.switch_to_window(window_handle)
            self.close()
        self.switch_to_window(main_window_handle)

    def close_alert(self, ignore_exception=False):
        """
        JS alerts all blocking. This method closes it. If there is no alert,
        method raises exception. In tests is good to call this method with
        ``ignore_exception`` setted to ``True`` which will ignore any exception.
        """
        try:
            alert = self.get_alert()
            alert.accept()
        except:
            if not ignore_exception:
                raise

    def get_alert(self):
        """
        Returns instance of :py:obj:`~selenium.webdriver.common.alert.Alert`.
        """
        return Alert(self)

    def download_url(self, url=None):
        """
        With WebDriver you can't check status code or headers. For this you have
        to make classic request. But web pages needs cookies and by this it gets
        ugly. You can easily use this method.

        When you not pass ``url``,
        :py:attr:`~selenium.webdriver.remote.webdriver.WebDriver.current_url`
        will be used.

        Returns :py:obj:`~webdriverwrapper.download._Download` instance.
        """
        return DownloadUrl(self, url)

    def fill_out_and_submit(self, data, prefix='', turbo=False):
        """
        Shortcut for filling out first ``<form>`` on page. See
        :py:class:`~webdriverwrapper.forms.Form` for more information.

        .. versionadded:: 2.0
        """
        return self.get_elm(tag_name='form').fill_out_and_submit(data, prefix, turbo)

    def fill_out(self, data, prefix='', turbo=False):
        """
        Shortcut for filling out first ``<form>`` on page. See
        :py:class:`~webdriverwrapper.forms.Form` for more information.

        .. versionadded:: 2.0
        """
        return self.get_elm(tag_name='form').fill_out(data, prefix, turbo)


class _WebElementWrapper(_WebdriverBaseWrapper, WebElement):
    """
    Class wrapping :py:class:`selenium.WebElement <selenium.webdriver.remote.webelement.WebElement>`.
    """

    def __new__(cls, webelement):
        instance = super(_WebElementWrapper, cls).__new__(cls)
        instance.__dict__.update(webelement.__dict__)
        return instance

    def __init__(self, webelement):
        # Nothing to do because whole __dict__ of original WebElement was
        # copied during creation of instance.
        pass

    @property
    def current_url(self):
        """
        Accessing :py:attr:`~selenium.webdriver.remote.webdriver.WebDriver.current_url`
        also on elements.
        """
        try:
            current_url = self._parent.current_url
        except Exception:
            current_url = 'unknown'
        finally:
            return current_url

    def download_file(self):
        """
        With WebDriver you can't check status code or headers. For this you have
        to make classic request. But web pages needs cookies and data from forms
        and by this it gets pretty ugly. You can easily use this method.

        It can handle downloading of page/file by link or any type of form.

        Returns :py:obj:`~webdriverwrapper.download._Download` instance.
        """
        return DownloadFile(self)


class _SelectWrapper(_WebElementWrapper, Select):
    def __init__(self, webelement):
        #  WebElementWrapper is created by coping __dict__ of WebElement instance
        #+ in method __new__ of _WebElementWrapper. So there have to be called
        #+ only init method of Select.
        Select.__init__(self, webelement)


class Chrome(_WebdriverWrapper, Chrome):
    pass


class Firefox(_WebdriverWrapper, Firefox):
    pass


class Ie(_WebdriverWrapper, Ie):
    pass


class Opera(_WebdriverWrapper, Opera):
    pass


class PhantomJS(_WebdriverWrapper, PhantomJS):
    pass


class Remote(_WebdriverWrapper, Remote):
    pass
