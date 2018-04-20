import io
import os
import typing

from compiler.bytecode_generator import BytecodeGenerator
from compiler.error import Error as CompilerError
from compiler.parser import Parser
from compiler.scanner import Scanner
from compiler.source_location import SourceLocation
from vm.error import Error as VMError, MissingArgumentError
from vm.executable import Executable
from vm.interpreter import Interpreter
from vm.bytecode import Opcode
from vm.value import Value, ValueType


class OYC:
    def __init__(self) -> None:
        self._file_path_2_module_value = {}

    def run_script(self, file_path: str, arguments: typing.List[str]) -> Value:
        file_path = os.path.abspath(file_path)
        self._file_path_2_module_value[file_path] = _MODULE_VALUE_PLACEHOLDER

        with open(file_path, "r") as f:
            source_location, executable = self._compile_script(f)

        arguments = [Value(ValueType.STRING, argument) for argument in arguments]
        interpreter = Interpreter(_MAX_STACK_DEPTH, self._builtin_require_impl)

        try:
            module_value = interpreter.run(source_location, executable, 0, arguments)
        except VMError as error:
            stack_trace = interpreter.get_stack_trace()
            message = "stack trace:\n"

            for source_location in reversed(stack_trace):
                message += "\t" + str(source_location) + "\n"

            message += "runtime error: " + str(error)
            raise SystemExit(message)

        self._file_path_2_module_value[file_path] = module_value
        return module_value

    def dump_bytecode(self, file_path: str):
        file_path = os.path.abspath(file_path)

        with open(file_path, "r") as f:
            _, executable = self._compile_script(f)

        for function_prototype_id in executable.get_function_prototype_ids():
            print("# ----- function prototype {} -----".format(function_prototype_id))
            function_prototype = executable.get_function_prototype(function_prototype_id)

            for instruction_offset, opcode, operand1, operand2, operand3, operand4 \
                in function_prototype.get_instructions(0):

                print("{}: {} {}, {}, {}".format(instruction_offset, opcode.name, operand1, operand2
                                                 , operand3), end = "")

                if operand4 is not None:
                    print(", {}".format(operand4), end = "")

                    if opcode == Opcode.LOAD_CONSTANT:
                        constant_id = operand4
                        constant = executable.get_constant(constant_id)
                        print(" # {}".format(repr(constant.data)), end = "")

                print("")

    def _compile_script(self, input_stream: io.IOBase) -> typing.Tuple[SourceLocation, Executable]:
        scanner = Scanner(input_stream)
        parser = Parser(scanner)
        bytecode_generator = BytecodeGenerator(parser)
        source_location = scanner.get_source_location()

        try:
            executable = bytecode_generator.get_executable()
        except CompilerError as error:
            raise SystemExit("compilation error: " + str(error))

        return source_location, executable

    def _builtin_require_impl(self, interpreter: Interpreter, source_location: SourceLocation
                              , stack_base: int, arguments: typing.List[Value]) -> Value:
        if len(arguments) == 0:
            raise MissingArgumentError(source_location)

        if arguments[0].type is not ValueType.STRING:
            raise VMError(source_location, "require() failed: file path must be a string")

        file_path = os.path.abspath(arguments[0].data)
        module_value = self._file_path_2_module_value.get(file_path)

        if module_value is _MODULE_VALUE_PLACEHOLDER:
            raise VMError(source_location, "require() failed: circular dependency")

        if module_value is None:
            self._file_path_2_module_value[file_path] = _MODULE_VALUE_PLACEHOLDER

            with open(file_path, "r") as f:
                _, executable = self._compile_script(f)

            module_value = interpreter.run(source_location, executable, stack_base, arguments[1:])
            self._file_path_2_module_value[file_path] = module_value

        return module_value


_MODULE_VALUE_PLACEHOLDER = False
_MAX_STACK_DEPTH = 64 * 1024


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2 or (sys.argv[1] == "-d" and len(sys.argv) < 3):
        message = """\
usage: {} [-d] <script> [arg] ...
options:
     -d dump bytecode
""".format(sys.argv[0])
        raise SystemExit(message)

    oyc = OYC()

    if sys.argv[1] == "-d":
        oyc.dump_bytecode(sys.argv[2])
    else:
        module_value = oyc.run_script(sys.argv[1], sys.argv[2:])

        if module_value.type is ValueType.INTEGER:
            code = module_value.data
        elif module_value.type is ValueType.VOID:
            code = 0
        else:
            code = 1

        sys.exit(code)
