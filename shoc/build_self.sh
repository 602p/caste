set -e
cd src

if [[ "${@#--no-unwind}" = "$@" ]]
then
    ../shoc_good main.ort -oshoc "--gcc_x../../lib/unwind/unwind_shim.o -lunwind" $@
else
    ../shoc_good main.ort -oshoc -s../../lib/nounwind_shim $@
fi

mv shoc ../shoc
cd ..