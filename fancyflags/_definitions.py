# Copyright 2021 DeepMind Technologies Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or  implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Structured dict flag."""

import collections
from absl import flags

from fancyflags import _argument_parsers
# internal imports: usage_logging

SEPARATOR = "."
_EMPTY = ""  # Empty serialized value returned by a dict flag.

# Add this module to absl's exclusion set for determining the calling modules.
flags.disclaim_key_flags()


def DEFINE_dict(*args, **kwargs):  # pylint: disable=invalid-name
  """Defines a flat or nested dictionary flag.

  Usage example:

  ```python
  import fancyflags as ff

  ff.DEFINE_dict(
      "image_settings",
      mode=ff.String("pad", "Mode string field."),
      sizes=dict(
          width=ff.Integer(5, "Width."),
          height=ff.Integer(7, "Height."),
          scale=ff.Float(0.5, "Scale.")
      )
  )

  This creates a flag `FLAGS.image_settings`, with a default value of

  ```python
  {
      "mode": "pad",
      "sizes": {
          "width": 5,
          "height": 7,
          "scale": 0.5,
      }
  }
  ```

  Each item in the definition (e.g. ff.Integer(...)) corresponds to a flag that
  can be overridden from the command line using "dot" notation. For example, the
  following command overrides the `height` item in the nested dictionary defined
  above:

  ```
  python script_name.py -- --image_settings.sizes.height=10
  ```

  Args:
    *args: One or two positional arguments are expected:
        1. A string containing the root name for this flag. This must be set.
        2. Optionally, a `flags.FlagValues` object that will hold the Flags.
           If not set, the usual global `flags.FLAGS` object will be used.
    **kwargs: One or more keyword arguments, where the value is either an
      `ff.Item` such as `ff.String(...)` or `ff.Integer(...)` or a dict with the
      same constraints.

  Returns:
    A `FlagHolder` instance.
  """
  if not args:
    raise ValueError("Please supply one positional argument containing the "
                     "top-level flag name for the dict.")

  if not kwargs:
    raise ValueError("Please supply at least one keyword argument defining a "
                     "flag.""")
  if len(args) > 2:
    raise ValueError("Please supply at most two positional arguments, the "
                     "first containing the top-level flag name for the dict "
                     "and, optionally and unusually, a second positional "
                     "argument to override the flags.FlagValues instance to "
                     "use.")

  if not isinstance(args[0], str):
    raise ValueError("The first positional argument must be a string "
                     "containing top-level flag name for the dict. Got a {}.".
                     format(type(args[0]).__name__))

  if len(args) == 2:
    if not isinstance(args[1], flags.FlagValues):
      raise ValueError("If supplying a second positional argument, this must "
                       "be a flags.FlagValues instance. Got a {}. If you meant "
                       "to define a flag, note these must be supplied as "
                       "keyword arguments. ".format(type(args[1]).__name__))
    flag_values = args[1]
  else:
    flag_values = flags.FLAGS

  flag_name = args[0]

  shared_dict = define_flags(flag_name, kwargs, flag_values=flag_values)

  # usage_logging: dict

  # TODO(b/177672282): Can we persuade pytype to correctly infer the type of the
  #                    flagholder's .value attribute?
  # We register a dummy flag that returns `shared_dict` as a value.
  return flags.DEFINE_flag(
      _DictFlag(
          shared_dict,
          name=flag_name,
          default=shared_dict,
          parser=flags.ArgumentParser(),
          serializer=None,
          help_string="Unused help string."),
      flag_values=flag_values)


def define_flags(name, deferred_flags, flag_values=flags.FLAGS):
  """Defines dot-delimited flags from a flat or nested dict of `ff.Item`s.

  Args:
    name: The top-level name to prepend to each flag.
    deferred_flags: A flat or nested dictionary, where each final value is an
      `ff.Item` such as `ff.String(...)` or `ff.Integer(...)`.
    flag_values: The `flags.FlagValues` instance to use. By default this is
      `flags.FLAGS`. Most users will not need to override this.

  Returns:
    A flat or nested dictionary containing the default values in
    `deferred_flags`. Overriding any of the flags defined by this function will
    also updated the corresponding entry in the returned dictionary.
  """
  # Each flag that we will define holds a reference to  `shared_dict`, which is
  # a flat or nested dictionary containing the default values.

  shared_dict = _extract_defaults(deferred_flags)

  # We create flags for each leaf item (e.g. ff.Integer(...)).

  # These are the flags that users will actually interact with when overriding
  # flags from the command line, however they will not access directly in their
  # scripts. It is also the job of these flags to update the corresponding
  # values in `shared_dict`, whenever their own values change.

  def recursively_define_flags(namespace, maybe_definition):
    if isinstance(maybe_definition, dict):
      for key, value in maybe_definition.items():
        recursively_define_flags(namespace + (key,), value)
    else:
      maybe_definition.define(namespace, {name: shared_dict}, flag_values)

  for key, value in deferred_flags.items():
    recursively_define_flags(namespace=(name, key), maybe_definition=value)

  return shared_dict


class _DictFlag(flags.Flag):
  """Implements the shared dict mechanism. See also _ItemFlag."""

  def __init__(self, shared_dict, *args, **kwargs):
    self._shared_dict = shared_dict
    super().__init__(*args, **kwargs)

  def _parse(self, value):
    # A dict flag should not be overridable from the command line; only the
    # dotted Item flags should be. However, the _parse() method will still be
    # called in two situations:

    # 1. In the base Flag's __init__ method, which calls _parse() to process the
    #    default value, which will be the shared dict.
    # 2. When processing command line overrides. We don't want to allow this
    #    normally, however some libraries will serialize and deserialize all
    #    flags, e.g. to pass values between processes, so we accept a dummy
    #    empty serialized value for these cases. It's unlikely users will try to
    #    set the dict flag to an empty string from the command line.
    if value is self._shared_dict or value == _EMPTY:
      return self._shared_dict
    raise flags.IllegalFlagValueError(
        "Can't override a dict flag directly. Did you mean to override one of "
        "its `Item`s instead?")

  def serialize(self):
    return _EMPTY

  def flag_type(self):
    return "dict"


# TODO(b/170423907): Pytype doesn't correctly infer that these have type
#                    `property`.
_flag_value_property = flags.Flag.value  # type: property
_multi_flag_value_property = flags.MultiFlag.value  # type: property


class _ItemFlag(flags.Flag):
  """Updates a shared dict whenever its own value changes.

  See also the _DictFlag and Item classes for usage.
  """

  def __init__(self, shared_dict, namespace, *args, **kwargs):
    self._shared_dict = shared_dict
    self._namespace = namespace
    super().__init__(*args, **kwargs)

  # `super().value = value` doesn't work, see https://bugs.python.org/issue14965
  @_flag_value_property.setter
  def value(self, value):
    _flag_value_property.fset(self, value)
    self._update_shared_dict()

  def parse(self, argument):
    super().parse(argument)
    self._update_shared_dict()

  def _update_shared_dict(self):
    d = self._shared_dict
    for name in self._namespace[:-1]:
      d = d[name]
    d[self._namespace[-1]] = self.value


class _MultiFlag(flags.MultiFlag):
  """Updates a shared dict whenever its own value changes.

  Used for flags that can appear multiple times on the command line.
  See also the _DictFlag and Item classes for usage.
  """

  def __init__(self, shared_dict, namespace, *args, **kwargs):
    self._shared_dict = shared_dict
    self._namespace = namespace
    super().__init__(*args, **kwargs)

  # `super().value = value` doesn't work, see https://bugs.python.org/issue14965
  @_multi_flag_value_property.setter
  def value(self, value):
    _multi_flag_value_property.fset(self, value)
    self._update_shared_dict()

  def parse(self, argument):
    super().parse(argument)
    self._update_shared_dict()

  def _update_shared_dict(self):
    d = self._shared_dict
    for name in self._namespace[:-1]:
      d = d[name]
    d[self._namespace[-1]] = self.value

# Public flag items.


class Item:
  """Defines a flag for leaf items in the dictionary."""

  def __init__(self, default, help_string, parser, serializer=None):
    """Initializes a new `Item`.

    Args:
      default: Default value of the flag that this instance will create.
      help_string: Help string for the flag that this instance will create.
      parser: A `flags.ArgumentParser` used to parse command line input.
      serializer: An optional custom `flags.ArgumentSerializer`. By default, the
        flag defined by this class will use an instance of the base
        `flags.ArgumentSerializer`.
    """
    # Flags run the following lines of parsing code during initialization.
    # See Flag._set_default in absl/flags/_flag.py

    # It's useful to repeat it here so that users will see any errors when the
    # Item is initialized, rather than when define() is called later.

    # The only minor difference is that Flag._set_default calls Flag._parse,
    # which also catches and modifies the exception type.
    if default is None:
      self.default = default
    else:
      self.default = parser.parse(default)

    self._help_string = help_string
    self._parser = parser

    if serializer is None:
      self._serializer = flags.ArgumentSerializer()
    else:
      self._serializer = serializer

  def define(self, namespace, shared_dict, flag_values):
    """Defines a flag that when parsed will update a shared dictionary.

    Args:
      namespace: A sequence of strings that define the name of this flag. For
        example, `("foo", "bar")` will correspond to a flag named `foo.bar`.
      shared_dict: A dictionary that is shared by the top level dict flag. When
        the individual flag created by this method is parsed, it will also
        write the parsed value into `shared_dict`. The `namespace` determines
        the flat or nested key when storing the parsed value.
      flag_values: The `flags.FlagValues` instance to use.
    """
    flags.DEFINE_flag(
        _ItemFlag(
            shared_dict,
            namespace,
            parser=self._parser,
            serializer=self._serializer,
            name=SEPARATOR.join(namespace),
            default=self.default,
            help_string=self._help_string),
        flag_values=flag_values)


class MultiItem:
  """Class for items that can appear multiple times on the command line.

  See Item class for more details on methods and usage.
  """

  def __init__(self,
               default,
               help_string,
               parser,
               serializer=None):
    if default is None:
      self.default = default
    else:
      if (isinstance(default, collections.abc.Iterable) and
          not isinstance(default, (str, bytes))):
        # Convert all non-string iterables to lists.
        default = list(default)

      if not isinstance(default, list):
        # Turn single items into single-value lists.
        default = [default]

      # Ensure each individual value is well-formed.
      self.default = [parser.parse(item) for item in default]

    self._help_string = help_string
    self._parser = parser

    if serializer is None:
      self._serializer = flags.ArgumentSerializer()
    else:
      self._serializer = serializer

  def define(self, namespace, shared_dict, flag_values):
    flags.DEFINE_flag(
        _MultiFlag(
            shared_dict,
            namespace,
            parser=self._parser,
            serializer=self._serializer,
            name=SEPARATOR.join(namespace),
            default=self.default,
            help_string=self._help_string),
        flag_values=flag_values)


class String(Item):

  def __init__(self, default, help_string):
    super().__init__(default, help_string, flags.ArgumentParser())


class MultiString(MultiItem):

  def __init__(self, default, help_string):
    parser = flags.ArgumentParser()
    serializer = flags.ArgumentSerializer()
    super().__init__(default, help_string, parser, serializer)


def DEFINE_multi_string(  # pylint: disable=invalid-name,redefined-builtin
    name, default, help, **args):
  """Defines flag for MultiString."""
  parser = flags.ArgumentParser()
  serializer = flags.ArgumentSerializer()
  # usage_logging: multi_string
  flags.DEFINE_multi(parser, serializer, name, default, help, **args)


class Float(Item):

  def __init__(self, default, help_string):
    super().__init__(default, help_string, flags.FloatParser())


class Integer(Item):

  def __init__(self, default, help_string):
    super().__init__(default, help_string, flags.IntegerParser())


class Boolean(Item):

  def __init__(self, default, help_string):
    super().__init__(default, help_string, flags.BooleanParser())


class Enum(Item):

  def __init__(self, default, enum_values, help_string, case_sensitive=True):
    parser = flags.EnumParser(enum_values, case_sensitive)
    super().__init__(default, help_string, parser)


# TODO(b/177673597) Better document the different enum class options and
#                   possibly recommend some over others.


class EnumClass(Item):
  """Matches behaviour of flags.DEFINE_enum_class."""

  def __init__(self, default, enum_class, help_string):
    parser = flags.EnumClassParser(enum_class)
    super().__init__(default, help_string, parser)


class MultiEnumClass(MultiItem):
  """Matches behaviour of flags.DEFINE_multi_enum_class."""

  def __init__(self, default, enum_class, help_string):
    parser = flags.EnumClassParser(enum_class)
    super().__init__(default, help_string, parser)


class MultiEnum(Item):
  """Defines a flag for lists of values of any type, matched to enum_values."""

  def __init__(self, default, enum_values, help_string):
    parser = _argument_parsers.MultiEnumParser(enum_values)
    serializer = flags.ArgumentSerializer()
    _ = parser.parse(enum_values)
    super().__init__(default, help_string, parser, serializer)


def DEFINE_multi_enum(  # pylint: disable=invalid-name,redefined-builtin
    name, default, enum_values, help, flag_values=flags.FLAGS, **args):
  """Defines flag for MultiEnum."""
  parser = _argument_parsers.MultiEnumParser(enum_values)
  serializer = flags.ArgumentSerializer()
  # usage_logging: multi_enum
  flags.DEFINE(parser, name, default, help, flag_values, serializer, **args)


class Sequence(Item):
  r"""Defines a flag for a list or tuple of simple numeric types or strings.

  Here is an example of overriding a Sequence flag within a dict-flag named
  "settings" from the command line, with a list of values.

  ```
  --settings.sequence=[1,2,3]
  ```

  To include spaces, either quote the entire literal, or escape spaces as:

  ```
  --settings.sequence="[1, 2, 3]"
  --settings.sequence=[1,\ 2,\ 3]
  ```
  """

  def __init__(self, default, help_string):
    super().__init__(default, help_string, _argument_parsers.SequenceParser())


def DEFINE_sequence(  # pylint: disable=invalid-name,redefined-builtin
    name, default, help, flag_values=flags.FLAGS, **args):
  """Defines a flag for a list or tuple of simple types. See `Sequence` docs."""
  parser = _argument_parsers.SequenceParser()
  serializer = flags.ArgumentSerializer()
  # usage_logging: sequence
  flags.DEFINE(parser, name, default, help, flag_values, serializer, **args)


class StringList(Item):
  """A flag that implements the same behavior as absl.flags.DEFINE_list.

  Can be overwritten as --my_flag="a,list,of,commaseparated,strings"
  """

  def __init__(self, default, help_string):
    serializer = flags.CsvListSerializer(",")
    super().__init__(default, help_string, flags.ListParser(), serializer)


def _extract_defaults(mapping):
  """Converts a flat or nested dict into a flat or nested dict of defaults."""

  result = {}
  for key, value in mapping.items():
    if isinstance(value, (Item, MultiItem)):
      result[key] = value.default
    elif isinstance(value, dict):
      result[key] = _extract_defaults(value)
    else:
      type_name = type(value).__name__
      raise TypeError("DEFINE_dict only supports flat or nested dictionaries, "
                      "and these must contain `ff.Item`s or `ff.MultiItems. "
                      "Found type {} in this definition.".format(type_name))
  return result
