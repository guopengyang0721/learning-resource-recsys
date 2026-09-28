# -*- coding: utf-8 -*-
"""CDP 驱动 Edge：登录后点击"个人中心"等页签，检查渲染与 JS 错误"""
import json
import time
import urllib.request

import websocket

targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=10).read())
page = next(t for t in targets if t['type'] == 'page' and '127.0.0.1:8000' in t.get('url', ''))
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=15, origin='http://127.0.0.1:9222')

mid = [0]


def ev(expr):
    mid[0] += 1
    ws.send(json.dumps({'id': mid[0], 'method': 'Runtime.evaluate',
                        'params': {'expression': expr, 'awaitPromise': True, 'returnByValue': True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get('id') == mid[0]:
            return msg['result']['result'].get('value')


def js(code):
    return ev(code)


def click_tab(name):
    return js('(function(){var t=Array.from(document.querySelectorAll(".el-tabs__item"))'
              '.find(e=>e.textContent.includes("%s")); if(!t) return "TAB_NOT_FOUND"; t.click(); return "clicked";})()' % name)


js("window.__errs=[]; window.addEventListener('error', e=>window.__errs.push(String(e.message)));")
time.sleep(2)

print('== 初始状态 ==')
print('页签:', js('Array.from(document.querySelectorAll(".el-tabs__item")).map(e=>e.textContent.trim()).join(" | ")'))
print('激活:', js('document.querySelector(".el-tabs__item.is-active")?.textContent.trim()'))

print('\n== 点击「个人中心」 ==')
print(click_tab('个人中心'))
time.sleep(2)
print('激活:', js('document.querySelector(".el-tabs__item.is-active")?.textContent.trim()'))
print('子导航按钮数:', js('document.querySelectorAll(".el-radio-button").length'))
print('整页含"个人信息":', js('document.body.innerText.includes("个人信息")'))
print('整页含"我的足迹":', js('document.body.innerText.includes("我的足迹")'))
print('整页含"编辑资料":', js('document.body.innerText.includes("编辑资料")'))

print('\n== 子页切换：我的足迹 ==')
print(js('(function(){var b=Array.from(document.querySelectorAll(".el-radio-button")).find(e=>e.textContent.includes("我的足迹")); if(!b) return "BTN_NOT_FOUND"; b.querySelector("input")?.click(); b.click(); return "clicked";})()'))
time.sleep(1.5)
print('整页含"行为记录表格(删除列)":', js('document.body.innerText.includes("删除") && document.body.innerText.includes("行为")'))

print('\n== 子页切换：我的收藏 ==')
print(js('(function(){var b=Array.from(document.querySelectorAll(".el-radio-button")).find(e=>e.textContent.includes("我的收藏")); if(!b) return "BTN_NOT_FOUND"; b.querySelector("input")?.click(); b.click(); return "clicked";})()'))
time.sleep(1.5)
print('整页含"暂无收藏"或收藏卡:', js('document.body.innerText.includes("暂无收藏") || document.body.innerText.includes("收藏于")'))

print('\n== 回到推荐页打开详情弹窗，点击"看了又看"项 ==')
click_tab('个性化推荐')
time.sleep(2)
print('点击推荐卡:', js('(function(){var c=document.querySelector(".el-col .el-card"); if(!c) return "CARD_NOT_FOUND"; c.click(); return "clicked";})()'))
time.sleep(2)
print('弹窗出现:', js('!!document.querySelector(".el-dialog")'))
print('弹窗标题:', js('document.querySelector(".el-dialog__title")?.textContent.trim()'))
print('看了又看项数:', js('document.querySelectorAll(".el-dialog .el-divider + h4 ~ div > div, .el-dialog").length'))
print('点击弹窗内相似项:', js('(function(){var items=Array.from(document.querySelectorAll(".el-dialog__body div")).filter(d=>d.textContent.includes("相似度")); if(!items.length) return "ITEM_NOT_FOUND"; items[0].click(); return "clicked";})()'))
time.sleep(2)
print('弹窗标题(应变化):', js('document.querySelector(".el-dialog__title")?.textContent.trim()'))
print('JS错误汇总:', js('JSON.stringify(window.__errs)'))

ws.close()
