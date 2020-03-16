import requests
from fake_useragent import UserAgent
from lxml import etree
from http import cookiejar
import re, time
import pymysql
import random
from requests.exceptions import Timeout

ua = UserAgent()

session = requests.Session()


class MyException(Exception):
    '''自定义一个异常'''

    def __init__(self, status, msg):
        self.status = status
        self.msg = msg
        super().__init__()


class AnKeJu:
    '''
    北京新房   https://bj.fang.anjuke.com/
    北京二手房 https://beijing.anjuke.com/sale/
    北京租房   https://bj.zu.anjuke.com/
    想要爬取不同城市的信息，只需将bj改为对应的城市信息
    '''

    # 本来想写下登陆的，但是他好像没有密码登陆，只有手机验证码。我说的普通用户
    is_login = False
    city_dict = {}
    conn = None
    proxies = None

    def __init__(self):
        self.session = session
        self.session.headers = {
            "user-agent": ua.random
        }
        self.session.cookies = cookiejar.LWPCookieJar(filename="./cookies.txt")

        if not self.conn:
            self.conn = pymysql.connect(host="127.0.0.1",
                                        port=3306,
                                        user="root",
                                        db="ankeju")
            self.conn.cursor = self.conn.cursor(cursor=pymysql.cursors.DictCursor)
        self.__get_all_city()

    def __response_to_xml(self, response):
        '''将response处理为xml格式数据'''
        xml = etree.HTML(response.text)
        return xml

    def __get_all_city(self):
        api = "https://www.anjuke.com/sy-city.html"
        headers = self.session.headers.copy()
        response = self.session.get(api, headers=headers)
        xml = self.__response_to_xml(response)
        city_xpath_list = xml.xpath("//div[@class='city_list']")[0:-1]
        city_name_list = [city_xpath.xpath("a/text()") for city_xpath in city_xpath_list]
        city_url_list = [city_xpath.xpath("a/@href") for city_xpath in city_xpath_list]
        city_dict_value = []
        city_dict_key = []

        # 这里真不知道怎么取变量名了
        # city_url_list它的格式是list套多个list，因为这个页面是按照A,B,C,D...这样排的
        for letter_url_list in city_url_list:
            for city_url in letter_url_list:
                shorthand_city = re.findall(r"//(.*?)\.", city_url)[0]
                city_dict_value.append(shorthand_city)

        for aa_list in city_name_list:
            for city_name in aa_list:
                city_dict_key.append(city_name)

        self.city_dict = {k: v for k, v in zip(city_dict_key, city_dict_value)}

    def __is_exist_next_page(self, response):
        '''判断二手房当前页面是否存在下一页'''
        xml = self.__response_to_xml(response)
        next_page_url = xml.xpath("//*[@class='aNxt']/@href")
        if next_page_url:
            return next_page_url[0]
        return False

    def __get_html_information_v2(self, response):
        '''获取二手房当前页面的房子信息'''
        xml = self.__response_to_xml(response)

        # 检测是不是访问验证的页面

        if xml.xpath("//*[@id='verify_page']"):
            # 出现了爬虫检测
            # 只要你的ip地址，都会出现访问验证这个页面，我也不清楚我用了代理，还是被检测出了ip问题
            # 那只有调用selenium去进行破解了
            pass

        # 获取到房子的信息
        li_xpath_list = xml.xpath("//*[@id='houselist-mod-new']//li[@class='list-item']")
        for li_xpath in li_xpath_list:
            house_info = []
            # 获取房子的img地址
            house_img_url = li_xpath.xpath("div[@class='item-img']/img/@src")[0]
            house_info.append(house_img_url)

            # 获取介绍房子的title
            house_title = li_xpath.xpath("div[@class='house-details']/div[1]/a/text()")[0].strip()
            house_info.append(house_title)
            # 获取房子详情信息
            house_details = li_xpath.xpath("div[@class='house-details']/div[2]")[0].xpath("string(.)").strip().split(
                "")[0]
            house_info.append(house_details)
            # 获取房子地址 可能会存在地址没有的请求
            try:
                house_address = li_xpath.xpath("div[@class='house-details']/div[3]/span/@title")[
                                    0].strip() or "暂时没有地址信息"
            except IndexError:
                house_address = "暂时没有地址信息"
            house_info.append(house_address)
            # 获取房子的总价钱
            house_total_price = li_xpath.xpath("div[@class='pro-price']/span[1]")[0].xpath("string(.)").strip()
            house_info.append(house_total_price)
            # 获取房子的房价
            house_price = li_xpath.xpath("div[@class='pro-price']/span[2]/text()")[0]
            house_info.append(house_price)
            # 获取房子标签
            house_tags = li_xpath.xpath("div[@class='house-details']/div[@class='tags-bottom']")[0].xpath(
                "string(.)").strip() or "暂无房子标签信息"

            house_info.append(house_tags)
            yield house_info

    def __get_html_information_v1(self, response):
        '''获取新房当前页面的房子信息'''
        xml = self.__response_to_xml(response)
        if xml.xpath("//*[@id='verify_page']"):
            pass

        div_xpath_list = xml.xpath("//div[@class='key-list imglazyload']//div[@class='item-mod ']")

        for div_xpath in div_xpath_list:
            house_info_list = []
            # 获取房子的img地址
            house_img_url = div_xpath.xpath("a[@class='pic']/img/@src")[0]
            house_info_list.append(house_img_url)
            # 获取介绍房子的title
            house_title = div_xpath.xpath("div[@class='infos']/a[@class='lp-name']/h3/span/text()")[0].strip()
            house_info_list.append(house_title)
            # 获取房子详情信息
            try:
                house_details = div_xpath.xpath("div[@class='infos']/a[@class='huxing']")[0].xpath("string(.)").strip()
                house_details = re.sub("\s", "", house_details)
            except IndexError:
                house_details = div_xpath.xpath("div[@class='infos']/a[@class='kp-time']/text()")[0]
            house_info_list.append(house_details)
            # 获取房子地址
            house_address = div_xpath.xpath("div[@class='infos']/a[@class='address']/span/text()")[0].strip()
            house_info_list.append(house_address)
            # 获取房子标签
            house_tags = ",".join(div_xpath.xpath("div[@class='infos']/a[@class='tags-wrap']/div/span/text()"))
            house_info_list.append(house_tags)
            # 获取房子的类型
            # 有些房子它是没有类型的
            try:
                house_type = \
                    div_xpath.xpath("div[@class='infos']/a[@class='tags-wrap']/div[@class='tag-panel']/i[2]/text()")[0]
            except IndexError:
                house_type = "无"
            house_info_list.append(house_type)
            # 获取房子是否还在售卖
            house_is_sale = div_xpath.xpath("div[@class='infos']/a[@class='tags-wrap']/div/i[1]/text()")[0]
            house_info_list.append(house_is_sale)
            # 获取房子价格
            # 有两种情况，一种价格确定，一种价格待定
            # 价格待定也有两种，一种是周围价格，一种就是没有价格
            try:
                house_price = div_xpath.xpath("a[@class='favor-pos']/p[@class='price']")[0].xpath("string(.)").strip()
            except IndexError:
                try:
                    house_price = div_xpath.xpath("a[@class='favor-pos']/p[2]")[0].xpath("string(.)").strip()
                except IndexError:
                    house_price = "暂无"
            house_info_list.append(house_price)
            yield house_info_list

    def __is_exist_next_page_v1(self, response):
        '''检测新房的当前页面是否有下一页'''
        xml = self.__response_to_xml(response)
        next_page_url = xml.xpath("//a[@class='next-page next-link']/@href")
        if next_page_url:
            return next_page_url[0]
        return False

    def __save_to_db(self, house_info_tuple, table_name):
        '''将数据保存在数据库,我这里只写了租房，新房，二手房，这样写的话，那么数据表的名字必须要对应上呀'''
        if table_name == "secondary_house":
            sql = "insert into secondary_house (house_img_url,house_title,house_details,house_address,house_total_price,house_price,house_tags) values (%s,%s,%s,%s,%s,%s,%s)"
        elif table_name == "new_house":
            sql = "insert into new_house (house_img_url,house_title,house_details,house_address,house_tags,house_type,house_is_sale,house_price) values (%s,%s,%s,%s,%s,%s,%s,%s)"

        else:
            sql = "insert into zu_house (house_img_url,house_title,house_details,house_address,house_tags,house_price) values (%s,%s,%s,%s,%s,%s)"
        self.conn.cursor.execute(sql, house_info_tuple)
        self.conn.commit()

    def __get_proxies(self):
        '''从代理池获取代理'''
        if not self.proxies:
            self.__init_proxies()
        while True:
            # 这里字段较少，而且所有的数据我都需要，所以用 "*"
            offset = random.randint(1, 100)
            sql = "select * from proxies ORDER BY id LIMIT %s,1 "
            row = self.proxies.cursor.execute(sql, (offset,))
            if not row:
                raise MyException(10003, "代理池错误")
            res = self.proxies.cursor.fetchone()
            proxies = {res["type"].lower(): "{}://{}:{}".format(res["type"].lower(), res["ip"], res["port"])}
            # 检测代理是否可以使用
            if self.__check_proxies(proxies):
                return proxies
            else:
                # 删除不可用的代理的记录
                del_sql = "DELETE FROM table_name where id = %s"
                self.proxies.cursor.execute(del_sql, (res["id"],))
                self.proxies.commit()

    def __check_proxies(self, proxies):
        '''检测代理是否可以使用'''
        api = "https://www.cnblogs.com/"
        try:
            res = requests.get(api, headers={"user-Agent": ua.random}, proxies=proxies, timeout=3)
            if res.status_code == 200:
                return True
            else:
                return False
        except Exception:
            return False

    def __init_proxies(self):
        self.proxies = pymysql.connect(
            host="127.0.0.1",
            port=3306,
            user="root",
            db="proxies"
        )
        self.proxies.cursor = self.proxies.cursor(cursor=pymysql.cursors.DictCursor)

    def __start_secondary_spider(self, url, city):
        '''处理二手房的爬虫'''
        secondary_house_table_name = "secondary_house"
        headers = self.session.headers
        page_num = 1
        while True:
            time.sleep(3)
            print("正在爬取 {} 第 {} 页...".format(city, page_num))
            response = self.session.get(url, headers=headers, proxies=self.__get_proxies(), timeout=10)

            # 获取当前页面的需要的数据,保存在数据库
            print("正在写入数据库...")

            for house_info_tuple in self.__get_html_information_v2(response):
                # 额，这里我是把所有的二手房信息，保存在一张表中，当时忘记加city这个字段了，如果你要写的话，最好加上city这个字段
                # 以后方便对数据库中的数据进行处理的话，就相对来说好很多
                self.__save_to_db(house_info_tuple, secondary_house_table_name)

            # 测试了一下，二手房数据最多50页，但是最好还是根据下一页去获取到下一页的数据
            next_page_url = self.__is_exist_next_page(response)
            if not next_page_url:
                raise MyException(10000, "{}二手房--数据爬取完毕...".format(city))
            url = next_page_url
            page_num += 1

    def __start_new_house_spider(self, url, city):
        '''处理新房的爬虫'''
        new_house_table_name = "new_house"
        headers = self.session.headers
        page_num = 1
        while True:
            time.sleep(3)
            print("正在爬取 {} 第 {} 页...".format(city, page_num))
            response = self.session.get(url, headers=headers, proxies=self.__get_proxies(), timeout=10)
            print("正在写入数据库...")
            for house_info_list in self.__get_html_information_v1(response):
                self.__save_to_db(house_info_list, new_house_table_name)
            next_page_url = self.__is_exist_next_page_v1(response)
            if not next_page_url:
                raise MyException(10000, "{}新房--数据爬取完毕...".format(city))
            url = next_page_url
            page_num += 1

    def __get_html_information_v3(self, response):
        '''获取租房页面的房子信息'''
        xml = self.__response_to_xml(response)
        if xml.xpath("//*[@id='verify_page']"):
            pass

        div_xpath_list = xml.xpath("//div[@class='zu-itemmod']")
        for div_xpath in div_xpath_list:
            house_info_list = []

            house_img_url = div_xpath.xpath("a/img/@src")[0]
            house_info_list.append(house_img_url)

            house_title = div_xpath.xpath("div[@class='zu-info']/h3/a/text()")[0].strip()
            house_info_list.append(house_title)

            house_details = div_xpath.xpath("div[@class='zu-info']/p[@class='details-item tag']")[0].xpath(
                "string(.)").strip().split("")[0]
            house_details = re.sub("\s", "", house_details)
            house_info_list.append(house_details)

            house_address = div_xpath.xpath("div[@class='zu-info']/address[@class='details-item']")[0].xpath(
                "string(.)").strip().replace("\xa0", "")
            house_address = re.sub("\s", "", house_address)
            house_info_list.append(house_address)

            house_tags = ",".join(div_xpath.xpath("div[@class='zu-info']/p[@class='details-item bot-tag']/span/text()"))
            house_info_list.append(house_tags)

            house_price = div_xpath.xpath("div[@class='zu-side']/p")[0].xpath("string(.)").strip()
            house_info_list.append(house_price)

            yield house_info_list

    def __is_exist_next_page_v3(self, response):
        '''判断租房页面是否有下一页'''
        xml = self.__response_to_xml(response)
        next_page_url = xml.xpath("//a[@class='aNxt']/@href")
        if next_page_url:
            return next_page_url[0]
        return False

    def __start_zu_house_spider(self, url, city):
        '''爬取租房'''
        zu_house_table_name = "zu_house"
        headers = self.session.headers
        page_num = 1
        while True:
            time.sleep(3)
            print("正在爬取 {} 第 {} 页...".format(city, page_num))
            try:
                response = self.session.get(url, headers=headers, proxies=self.__get_proxies(), timeout=10)
            except Timeout:
                response = self.session.get(url, headers=headers, proxies=self.__get_proxies(), timeout=10)
            print("正在写入数据库...")
            for house_info_list in self.__get_html_information_v3(response):
                self.__save_to_db(house_info_list, zu_house_table_name)
            next_page_url = self.__is_exist_next_page_v3(response)
            if not next_page_url:
                raise MyException(10000, "{}租房--数据爬取完毕...".format(city))
            url = next_page_url
            page_num += 1

    def spider_zufang(self, city: str = "北京", allow_all: bool = False):
        '''爬取租房信息'''
        while True:
            format_city = self.city_dict.pop(city)
            assert bool(format_city) is True, "请输入正确的地区"
            start_url = "https://{}.zu.anjuke.com/".format(format_city)
            try:
                self.__start_zu_house_spider(start_url, city)
            except MyException as e:
                if e.status == 10000:
                    print(e.msg)
                    if allow_all:
                        try:
                            city = list(self.city_dict.keys()).pop(0)
                        except IndexError:
                            print("全部爬取完毕")
                            return
                    else:
                        return

    def spider_new_house(self, city: str = "北京", allow_all: bool = False):
        '''爬取新房'''
        while True:
            format_city = self.city_dict.pop(city)
            assert bool(format_city) is True, "请输入正确的地区"
            start_url = "https://{}.fang.anjuke.com/".format(format_city)
            try:
                self.__start_new_house_spider(start_url, city)
            except MyException as e:
                if e.status == 10000:
                    print(e.msg)
                    if allow_all:
                        try:
                            city = list(self.city_dict.keys()).pop(0)
                        except IndexError:
                            print("全部爬取完毕")
                            return
                    else:
                        return

    def spider_secondary(self, city: str = "北京", allow_all: bool = False):
        '''
        :param city: 默认是北京
        :return:
        '''
        # 这里直接是要bj也是可以的，他会帮我们重定向beijing
        while True:
            format_city = self.city_dict.pop(city)
            assert bool(format_city) is True, "请输入正确的地区"
            start_url = "https://{}.anjuke.com/sale/".format(format_city)
            try:
                self.__start_secondary_spider(start_url, city)
            except MyException as e:
                if e.status == 10000:
                    print(e.msg)
                    if allow_all:
                        try:
                            city = list(self.city_dict.keys()).pop(0)
                        except IndexError:
                            print("全部爬取完毕")
                            return
                    else:
                        return

    def __del__(self):
        self.conn.close()
        if self.proxies:
            self.proxies.close()

    def test(self):
        '''测试bug专用方法'''
        res = self.session.get("https://al.zu.anjuke.com/", headers=self.session.headers)
        n = 1
        for i in self.__get_html_information_v3(res):
            print(n)
            print(i)
            n += 1


if __name__ == '__main__':
    anjuke = AnKeJu()
    # anjuke.spider_secondary(allow_all=True)
    # anjuke.spider_new_house(allow_all=True)
    # anjuke.spider_zufang(allow_all=True)
    # anjuke.test()