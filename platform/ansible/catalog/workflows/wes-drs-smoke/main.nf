nextflow.enable.dsl=2
workflow {
 log.info "DRS input: ${file(params.input).size()} bytes"
}
