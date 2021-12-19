# ctor

`ctor` is an object tree construction and deconstruction library.
It provides non-invasive way of constructing and deconstructing objects based on type annotations.

Installation:
```shell
pip install ctor
```

### Features
* 0 dependencies
* Your classes are yours! Library does not mess with your code.
  * No subclassing / metaclassing
  * No special class-level field annotations
  * Library does no replace/generate  `__init__` and/or other methods
* Works with `dataclasses`, `attrs`, `PyDantic` and even pure-python classes.
* Extendable if needed
* Supports `Union`, `Literal`, `Annotated`, forward references, cyclic-types ...
* PyCharm and other IDEs highlight constructor arguments natively without plugins
* Supports Python 3.7+


### Example with python dataclasses

```python
from dataclasses import dataclass  # standard python


@dataclass
class MyClass:
  name: str
  value: int

# some_other_file.py


#   note that this import might be in a different file 
#   so that your code remains untouched by serialization logic  
import ctor

# Dumping
my_object = MyClass(name='hello', value=42)
data = ctor.dump(my_object)
print(data)  # {'name': 'hello', 'value': 42}

# Loading
data = {'name': 'World', 'value': -42}
restored_object = ctor.load(MyClass, data)
print(restored_object)  # MyClass(name='world', value=-42)
```

### Nested objects with dataclasses

```python
from dataclasses import dataclass  # standard python
from typing import List


@dataclass
class TreeNode:
  name: str
  children: List['TreeNode']  # Note: forward reference making class cyclic


graph = TreeNode(name="root", children=[
  TreeNode(name="A", children=[]),
  TreeNode(name="B", children=[
    TreeNode(name="x", children=[]),
    TreeNode(name="y", children=[]),
  ]),
  TreeNode(name="C", children=[]),
])

# Note: Even in this complex scenario, classes and data are still untouched by the library code.
import ctor

graph_data = ctor.dump(graph)
print(
  graph_data)  # {'name': 'root', 'children': [{'name': 'A', 'children': []}, {'name': 'B', 'children': [{'name': 'x', 'children': []}, {'name': 'y', 'children': []}]}, {'name': 'C', 'children': []}]}
```

### Bare classes

```python
class User:
  def __init__(self, uid: int, email: str, name: str):
    self.uid = uid
    self.email = email
    self.name = name


class Post:
  def __init__(self, title: str, content: str, author: User):
    self.title = title
    self.content = content
    self.author = author


import
  ctor  # Import placed here just to highlight that your business-level code still does not require serialization library

data = {
  'content': 'Fields can go in any order also',
  'author': {
    'uid': 123,
    'email': 'john@doe.org',
    'name': 'John Doe'
  },
  'title': 'Unbelievable'
}
post = ctor.load(Post, data)  # post is a normal python object here
print(post.author.name)  # post.user is a User
```

Note that this is not just `Post(**data)` because you need to construct `User` object first.
This works with objects of any depth.

Implementation described lower in the README. 


## Running tests

* To test against current python version: `pytest`
* To tests all python versions: `tox --parallel`
