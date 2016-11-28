import collections, transform, types

magicmethods={
	"add":"__add__",
	"sub":"__sub__",
	"mul":"__mul__",
	"div":"__div__",
	"gt":"__gt__",
	"ge":"__ge__",
	"lt":"__lt__",
	"le":"__le__",
	"eq":"__eq__",
	"ne":"__ne__",
	"neg":"__neg__"
}

class OType:
	def __init__(self, name):
		def _make_caller(magic):
			def method(self, lhs, rhs, out):
				methname=name+"$"+magic
				return transform.call_func(
					methname,
					[t.type.get_llvm_representation() for t in out.signatures[methname].args],
					[lhs, rhs],
					out
				)
			return types.MethodType(method, self)

		self.name=name

		for k, v in magicmethods.items():
			if not hasattr(self, "implement_"+k):
				setattr(self, "implement_"+k, _make_caller(v))

	def implement_neg(self, lhs, out):
		return transform.call_func(
			self.name+"$__neg__",
			[t.type.get_llvm_representation() for t in out.signatures[self.name+"$__neg__"].args],
			[lhs, rhs],
			out
		)

	def get_llvm_representation(self):
		pass

	def __str__(self):
		return "t{"+self.name+"}"

	def __repr__(self):
		return str(self)

class PrimitiveOType(OType):
	def __init__(self, name, llvmtype):
		OType.__init__(self, name)
		self.llvmtype=llvmtype

	def get_llvm_representation(self):
		return self.llvmtype

class IntegerPrimitiveOType(PrimitiveOType):
	def __init__(self, name, llvmtype, literal_formatter):
		OType.__init__(self, name)
		self.llvmtype=llvmtype
		self.fields=None
		self.datalayout=None
		self.literal_formatter=literal_formatter

	def get_bit_width(self):
		return int(self.llvmtype[1:])

	def get_llvm_representation(self):
		return self.llvmtype

	def get_literal_expr(self, value, out):
		return self.literal_formatter.format(value)

	def implement_add(self, lhs, rhs, out):
		return "add {} %{}, %{}".format(self.get_llvm_representation(), lhs, rhs)

	def implement_sub(self, lhs, rhs, out):
		return "sub {} %{}, %{}".format(self.get_llvm_representation(), lhs, rhs)

	def implement_neg(self, val, out):
		return "sub {} %{}, 0".format(self.get_llvm_representation(), val)

	def implement_mul(self, lhs, rhs, out):
		return "mul {} %{}, %{}".format(self.get_llvm_representation(), lhs, rhs)

	def implement_div(self, lhs, rhs, out):
		return "sdiv {} %{}, %{}".format(self.get_llvm_representation(), lhs, rhs)

	def implement_gt(self, lhs, rhs, out):
		return "icmp sgt {} %{}, %{}".format(self.get_llvm_representation(), lhs, rhs)
	def implement_ge(self, lhs, rhs, out):
		return "icmp sge {} %{}, %{}".format(self.get_llvm_representation(), lhs, rhs)
	def implement_lt(self, lhs, rhs, out):
		return "icmp slt {} %{}, %{}".format(self.get_llvm_representation(), lhs, rhs)
	def implement_le(self, lhs, rhs, out):
		return "icmp sle {} %{}, %{}".format(self.get_llvm_representation(), lhs, rhs)
	def implement_eq(self, lhs, rhs, out):
		return "icmp eq {} %{}, %{}".format(self.get_llvm_representation(), lhs, rhs)
	def implement_ne(self, lhs, rhs, out):
		return "icmp ne {} %{}, %{}".format(self.get_llvm_representation(), lhs, rhs)

	def implement_cast(self, value, from_, to):
		if to.get_bit_width()>from_.get_bit_width():
			return "zext {} %{} to {}".format(
				from_.get_llvm_representation(),
				value,
				to.get_llvm_representation()
			)
		elif to.get_bit_width()==from_.get_bit_width():
			return "%"+value
		else:
			return "trunc {} %{} to {}".format(
				from_.get_llvm_representation(),
				value,
				to.get_llvm_representation()
			)

class FunctionOType(OType):
	def __init__(self, name, args, returntype):
		OType.__init__(self, name)
		self.llvmtype=returntype.get_llvm_representation()
		self.argsig=" ("+(",".join(typ.type.get_llvm_representation() for typ in args))+")"
		self.fields=None
		self.datalayout=None
		self.returntype=returntype
		self.args=args

	def get_llvm_representation(self):
		return self.llvmtype+" "+self.argsig

class ManualFunctionOType(FunctionOType):
	def __init__(self, name, argsig, returntype):
		FunctionOType.__init__(self, name, [], returntype)
		self.argsig=argsig
		self.llvmtype=returntype.get_llvm_representation()

class PrimitiveCStrOType(PrimitiveOType):
	def __init__(self, name, llvmtype):
		OType.__init__(self, name)
		self.llvmtype=llvmtype

	def get_literal_expr(self, value, out):
		globalname="strglobal_"+out.get_name()
		transformed="".join("\\{}".format(("0" if ord(char)<16 else "") + hex(ord(char))[2:]) for char in value)
		out.add_global_stmt("@{} = private unnamed_addr constant [{} x i8] c\"{}\" ; c={}".format(
			globalname,
			len(value)+1,
			transformed+"\\00",
			repr(value)
		))
		name=out.get_temp_name()
		out.emitl("%{} = getelementptr [{} x i8]* @{}".format(name, len(value)+1, globalname))
		return "bitcast [{} x i8]* %{} to i8*".format(
			len(value)+1,
			name
		)

class StructOType(OType):
	def __init__(self, name, fields):
		OType.__init__(self, name)
		self.fields=collections.OrderedDict(fields)
		self.datalayout=None

builtin_types = {e.name:e for e in [
	IntegerPrimitiveOType("bool", "i1", "add i1 0, {}"),
	IntegerPrimitiveOType("int", "i32", "add i32 0, {}"),
	IntegerPrimitiveOType("short", "i16", "add i16 0, {}"),
	IntegerPrimitiveOType("byte", "i8", "add i8 0, {}"),
	IntegerPrimitiveOType("long", "i64", "add i64 0, {}"),
	IntegerPrimitiveOType("xlong", "i128", "add i128 0, {}"),
	IntegerPrimitiveOType("xxlong", "i256", "add i256 0, {}"),
	PrimitiveOType("ptr", "i8*"),
	PrimitiveCStrOType("cstr", "i8*")
]}