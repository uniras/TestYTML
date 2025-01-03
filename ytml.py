"""
YTML (YAML Text Markup Language) モジュール

YAML準拠のマークアップをHTMLやテンプレートエンジンのテンプレートに変換するライブラリ

記法:

要素群をリストで列挙、各要素をキーが1つの辞書で表現。

キー名にタグ名と属性を記述する。最初の文字列はタグ名、属性はタグ名の後に括弧をつけて記述。

属性の記法は基本的にHTMLと同様だが、classは(.クラス名)で、idは(#id名)で記述することもできる。

属性は省略可能、タグ名を省略して属性のみを記述した場合はdivタグとして扱う。両方省略すると属性のないdivタグとして扱うが、YAMLの仕様上完全な空白にはできないので""を記述する必要がある。

値にリストを設定すると子要素を表現、値に文字列を指定するとコンテンツを表現。

HTML仕様でvoid要素として定義されているものは自動的に自己完結タグに変換する、値を設定するとエラー。

文字列は全てエスケープされ、基本的に文字列内に直接HTMLタグを書くことはできない。

YAMLの仕様として|等を使用して複数行の文字列を記述できるが、そのままテキストとして出力される。改行のために<br/>を入れたい場合はMarkdownと同様に末尾に2つの半角スペースを入れて改行する。

例:

- html(lang="ja"):
    - head:
        - meta(charset="UTF-8"):
        - title: "Hello, World!"
    - body:
        - h1: "Hello, World!"
        - p: "This is a sample page."
        - (.container): "This is a container."
        - (#test): "This is a id."

結果:

<html lang="ja">
    <head>
        <meta charset="UTF-8"/>
        <title>Hello, World!</title>
    </head>
    <body>
        <h1>Hello, World!</h1>
        <p>This is a sample page.</p>
        <div class="container">This is a container.</div>
        <div id="test">This is a id.</div>
    </body>
</html>
"""

import re


class PrettyFormatter:
    def __init__(self, indent_length: int = 4) -> None:
        self.indent_len = indent_length
        self.indent = 0

    # 条件リストを評価して処理を行うかを決定
    def apply_condition(self, conditions: list) -> bool:
        return all(conditions)

    # インデントを増加
    def add_indent(self, conditions: list = []) -> None:
        if self.apply_condition(conditions):
            self.indent += 1

    # インデントを減少
    def del_indent(self, conditions: list = []) -> None:
        if self.apply_condition(conditions) and self.indent > 0:
            self.indent -= 1

    # 現在のインデントに加算した値を取得(条件を満たさない場合は現在のインデントを返す)
    def get_add_indent(self, add: int = 0, conditions: list = []) -> int:
        if self.apply_condition(conditions):
            return self.indent + add
        return self.indent

    # 現在のインデントまたは引数に応じた空白を出力
    def output_space(self, conditions: list = [], level: int = -1) -> str:
        if self.apply_condition(conditions):
            val = level if level >= 0 else self.indent
            return ' ' * self.indent_len * val
        return ''

    # 改行を追加する場合の文字列
    def output_newline(self, conditions: list = []) -> str:
        return '\n' if self.apply_condition(conditions) else ''

    # インデントされたテキストを出力
    def output_indented_text(self, text: str, conditions: list = []) -> str:
        if self.apply_condition(conditions):
            result = ''
            for line in text.strip().split('\n'):
                result += self.output_space()
                result += line
                result += '\n'
            return result
        else:
            return text


# YTMLクラス
class YTML:
    # voidタグのリスト
    void_tags = ['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']

    # テンプレートタグのリスト
    template_tags = []

    # 自己完結テンプレートタグのリスト
    template_void_tags = []

    # テンプレートタグ名の変換リスト(空白はタグ自体出力しない), 3番目の要素は属性を出力するかどうか
    template_tag_convert = {}

    # テンプレートの終了タグで変数名(属性)を出力するかどうか(Mustache用)
    # templase_use_end_attr = False

    # テンプレート内の属性の先頭にスペースを追加しない(Mustache用)
    # template_attr_no_space = False

    # HTMLタグの開始・終了文字列
    html_tag_start = '<'
    html_tag_end = '>'
    html_tag_end_close = '</'
    html_tag_end_self_close = '/>'

    # テンプレートタグの開始・終了文字列
    template_tag_start = ''
    template_tag_end = ''
    template_tag_close = ''
    template_tag_self_close = ''

    # テンプレート変数の開始・終了文字列
    template_variable_start = ''
    template_variable_end = ''

    def init_flags(self):
        # フラグの初期化
        flags = {
            'isvoid': False,             # voidタグかどうか
            'tagname': '',               # タグ名
            'starttagname': '',          # 開始タグ名
            'endtagname': '',            # 終了タグ名
            'attr': '',                  # 属性文字列
            'attrspace': True,           # 属性の先頭にスペースを追加するかどうか
            'tagstart': '',              # 開始タグの開始文字列
            'tagend': '',                # 開始タグの終了文字列
            'closetagstart': '',         # 終了タグの開始文字列
            'longcontent': False,        # 子要素があるまたはコンテンツが複数行かどうか
            'usestart': True,            # 開始タグを使用するかどうか
            'useindent': True,           # インデントするかどうか
            'convertattr': True,         # 属性の.classや#idを変換するかどうか
            'useattr': True,             # 属性を使用するかどうか
            'forcetemplate': False,      # 強制的にテンプレートタグとみなすかどうか、テンプレートタグ一覧に存在しない場合はエラー
        }

        return flags

    def parse_dict(self, item: dict, flags: dict, pretty: bool, formatter: PrettyFormatter) -> any:
        # 辞書を解析してタグ名と属性を取得
        # itemが辞書でない場合はエラー
        if not isinstance(item, dict):
            raise ValueError('obj must be a list of dicts')

        # 辞書のキーが1つでない場合はエラー
        if len(item) != 1:
            raise ValueError('dicts in obj must have exactly one key')

        # キーと値を取得
        key, value = list(item.items())[0]

        # キーを解析
        matches = re.match(r'([^\(\)\s]+)?\s?\((.*)\)$', key)

        if matches:
            # 属性付きのキー名の場合、タグ名と属性を解析して取得
            flags['tagname'] = matches.group(1)
            flags['attr'] = matches.group(2)

            # タグ名がない場合はdivを設定
            if flags['tagname'] is None:
                flags['tagname'] = 'div'
        else:
            # 属性なしのキー名の場合、キー名をそのままタグ名として設定
            if key == '':
                # キー名が空の場合はdivを設定
                flags['tagname'] = 'div'
            else:
                flags['tagname'] = key

        if flags['tagname'][0] == '$':
            # 先頭に$があるタグ名は強制的にテンプレートタグとみなす
            flags['tagname'] = flags['tagname'][1:]
            flags['forcetemplate'] = True

        return value

    def set_tag_type(self, value: any, flags: dict, pretty: bool, formatter: PrettyFormatter) -> None:
        # タグ名からタグの種類を判別して設定
        if flags['forcetemplate']:
            # 強制的にテンプレートタグとみなしているがこのメソッドはHTMLタグ専用なのでエラー
            raise ValueError(f'not supported template tag: {flags['tagname']}')
        elif flags['tagname'] in self.void_tags:
            # HTMLのvoidタグの場合
            flags['isvoid'] = True
            flags['tagend'] = self.html_tag_end_self_close
        else:
            # 通常のHTMLタグの場合
            flags['tagend'] = self.html_tag_end
            flags['closetagstart'] = self.html_tag_end_close

        # HTMLタグ共通の設定
        flags['tagstart'] = self.html_tag_start
        flags['starttagname'] = flags['tagname']
        flags['endtagname'] = flags['tagname']

    def convert_attr(self, value: any, flags: dict, pretty: bool, formatter: PrettyFormatter) -> None:
        # 属性を変換
        if flags['useattr']:
            if flags['convertattr']:
                # .classや#idを属性に変換
                flags['attr'] = re.sub(r'\.(\S+)', 'class="\\1"', flags['attr'])
                flags['attr'] = re.sub(r'#(\S+)', 'id="\\1"', flags['attr'])

            # 属性の先頭にスペースを追加
            if flags['attrspace'] and flags['attr'] != '':
                flags['attr'] = ' ' + flags['attr']
        else:
            # 属性を使用しない場合は空文字列に設定
            flags['attr'] = ''

    def output_start_tag(self, value: any, flags: dict, pretty: bool, formatter: PrettyFormatter) -> str:
        # 開始タグを出力
        result = ''

        # void要素内に子要素やコンテンツがある場合はエラー
        if flags['isvoid'] and value is not None:
            raise ValueError('void tag must have no content')

        # 開始タグを出力
        if flags['starttagname'] != '':
            tagindent = formatter.get_add_indent(-1, [pretty, not flags['useindent']])
            result += formatter.output_space([pretty], tagindent)
            result += f'{flags['tagstart']}{flags['starttagname']}{flags['attr']}{flags['tagend']}'
        else:
            flags['usestart'] = False

        # void要素の場合は改行を追加
        if flags['isvoid']:
            result += formatter.output_newline([pretty])

        return result

    def parse_children(self, value: any, flags: dict, pretty: bool, formatter: PrettyFormatter) -> str:
        # 子要素・コンテンツを処理
        result = ''

        if isinstance(value, list):
            # 値がリストの場合は子要素として再帰的に処理
            flags['longcontent'] = True
            result += formatter.output_newline([pretty, flags['usestart']])
            formatter.add_indent([pretty, flags['useindent'], flags['usestart']])
            result += self.obj_to_html(value, pretty, formatter.indent_len, formatter)
        elif isinstance(value, str):
            # 値が文字列の場合はテンプレート変数を解析して追加
            value = re.sub(r'{{\s*(\S+)\s*}}', f'{self.template_variable_start}\\1{self.template_variable_end}', value)
            # HTMLエスケープ
            value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')
            # 半角スペース2つと改行が連続している場合はbrタグに変換(Markdownの仕様に準拠)
            value = re.sub(r'  \n', '<br/>\n', value)
            if value.find('\n') >= 0:
                result += formatter.output_newline([pretty])
                formatter.add_indent([pretty])
                flags['longcontent'] = True
            result += formatter.output_indented_text(value, [pretty, flags['longcontent']])
            result += formatter.output_newline([pretty, flags['longcontent']])
        elif value is None:
            # 値がNoneの場合はコンテンツが空の要素として処理
            pass
        else:
            # 値がリストでも文字列でも空でもない場合はエラー
            raise ValueError('value must be a list or a string')

        return result

    def output_endtag(self, value: any, flags: dict, pretty: bool, formatter: PrettyFormatter) -> str:
        # 終了タグを出力
        result = ''

        formatter.del_indent([pretty, flags['longcontent'], flags['useindent']])
        if flags['endtagname'] != '':
            result += formatter.output_space([pretty, flags['longcontent']])
            result += f'{flags['closetagstart']}{flags['endtagname']}{flags['tagend']}'
            result += formatter.output_newline([pretty])

        return result

    # YTML(yaml)から変換したオブジェクトをHTMLに変換
    def obj_to_html(self, obj: any, pretty: bool = False, indent_len: int = 4, formatter: PrettyFormatter = None) -> str:
        # objがリストでない場合はエラー
        if not isinstance(obj, list):
            raise ValueError('obj must be a list')

        result = ''  # 結果文字列

        # インデントフォーマッタが渡されなかった時は作成
        if formatter is None:
            formatter = PrettyFormatter(indent_len)

        # リストを走査
        for item in obj:
            # フラグの初期化
            flags = self.init_flags()

            # タグ名と属性を解析
            value = self.parse_dict(item, flags, pretty, formatter)

            # タグの種類を判別して設定
            self.set_tag_type(value, flags, pretty, formatter)

            # 属性を変換
            self.convert_attr(value, flags, pretty, formatter)

            # 開始タグを追加
            result += self.output_start_tag(value, flags, pretty, formatter)

            # void要素の場合はこの先の処理をスキップ
            if flags['isvoid']:
                continue

            # 子要素を解析
            result += self.parse_children(value, flags, pretty, formatter)

            # 終了タグを追加
            result += self.output_endtag(value, flags, pretty, formatter)

        return result

    # YTML形式の文字列をHTMLに変換
    def str_to_html(self, text: str, pretty: bool = False, indent_len: int = 4) -> str:
        # yaml形式の文字列を解析してHTMLに変換
        import yaml
        obj = yaml.load(text, Loader=yaml.FullLoader)
        return self.obj_to_html(obj, pretty, indent_len)


# Jinja2テンプレートエンジン対応クラス
class YTMLJinja(YTML):
    # テンプレートタグのリスト
    template_tags = ['for', 'if', 'then', 'elif', 'else', 'block', 'filter', 'macro', 'call', 'raw']

    # 自己完結テンプレートタグのリスト
    template_void_tags = ['include', 'extends', 'set']

    templase_use_end_attr = False
    template_tag_start = '{% '
    template_tag_end = ' %}'
    template_tag_close = '{% '
    template_tag_self_close = ' %}'

    template_tag_convert = {
        'for': ['for', 'endfor', True],
        'if': ['if', 'endif', True],
        'then': ['', '', False],
        'elif': ['elif', '', True],
        'else': ['else', '', False],
        'block': ['block', 'endblock', True],
        'filter': ['filter', 'endfilter', True],
        'macro': ['macro', 'endmacro', True],
        'call': ['call', 'endcall', True],
        'raw': ['raw', 'endraw', True],
        'include': ['include', '', True],
        'extends': ['extends', '', True],
        'set': ['set', '', True],
    }

    def set_tag_type(self, value: any, flags: dict, pretty: bool, formatter: PrettyFormatter) -> None:
        # タグ名に応じて出力動作の設定
        if flags['tagname'] in self.template_tags:
            # テンプレートタグの場合
            if flags['tagname'] not in self.template_tag_convert:
                raise ValueError(f'not supported template tag: {flags['tagname']}')
            flags['tagstart'] = self.template_tag_start
            flags['tagend'] = self.template_tag_end
            flags['closetagstart'] = self.template_tag_close
            flags['starttagname'] = self.template_tag_convert[flags['tagname']][0]
            flags['endtagname'] = self.template_tag_convert[flags['tagname']][1]
            flags['useindent'] = self.template_tag_convert[flags['tagname']][1] != ''
            flags['useattr'] = self.template_tag_convert[flags['tagname']][2]
            flags['convertattr'] = False
        elif flags['tagname'] in self.template_void_tags:
            # 自己完結テンプレートタグの場合
            if flags['tagname'] not in self.template_tag_convert:
                raise ValueError(f'not supported template tag: {flags['tagname']}')
            flags['isvoid'] = True
            flags['tagstart'] = self.template_tag_start
            flags['tagend'] = self.template_tag_self_close
            flags['starttagname'] = self.template_tag_convert[flags['tagname']][0]
            flags['useattr'] = self.template_tag_convert[flags['tagname']][2]
            flags['convertattr'] = False
        else:
            super().set_tag_type(value, flags, pretty, formatter)
