nextflow.enable.dsl=2

params.ref       = null
params.ref_fai   = null
params.ref_dict  = null
params.cram      = null
params.bed       = null
params.truth_vcf = null
params.sample_name = 'sample'

process GET_GATK {
  tag "getgatk"
  output:
    path 'gatk.jar'
  script:
    """
    curl -sSL --fail -o gatk.zip \\
      https://github.com/broadinstitute/gatk/releases/download/4.7.0.0/gatk-4.7.0.0.zip
    if command -v unzip > /dev/null 2>&1; then unzip -q gatk.zip
    elif command -v python3 > /dev/null 2>&1; then python3 -c "import zipfile; zipfile.ZipFile('gatk.zip').extractall('.')"
    else jar xf gatk.zip; fi
    cp gatk-4.7.0.0/gatk-package-4.7.0.0-local.jar gatk.jar
    ls -la gatk.jar
    rm -rf gatk.zip gatk-4.7.0.0
    """
}

process CALL {
  tag "${sample}"
  input:
    path gatk
    val sample
    path ref
    path ref_fai
    path ref_dict
    path cram
    path bed
  output:
    path 'called.vcf'
  script:
    """
    mv $ref ref.fa
    cp $ref_fai ref.fa.fai
    cp $ref_dict ref.dict
    java -Xms512m -Xmx6g -jar $gatk HaplotypeCaller \\
      -R ref.fa \\
      -I $cram \\
      -O called.vcf \\
      -L $bed \\
      --disable-sequence-dictionary-validation true
    """
}

process EVALUATE {
  tag "eval"
  input:
    path vcf
    path truth
  output:
    path 'summary.txt'
  script:
    """
    cat > CountVars.java <<'JAVA'
    import java.io.*;
    import java.util.zip.*;
    public class CountVars {
      public static void main(String[] a) throws Exception {
        long called = count(a[0]);
        long t      = count(a[1]);
        System.out.println("called_variants=" + called);
        System.out.println("truth_variants=" + t);
        System.out.println("called_vs_truth_ratio=" + (t > 0 ? String.format("%.3f", (double) called / t) : "n/a"));
      }
      static long count(String p) throws Exception {
        InputStream in = new FileInputStream(p);
        if (p.endsWith(".gz")) in = new GZIPInputStream(in);
        BufferedReader r = new BufferedReader(new InputStreamReader(in));
        long n = 0; String l;
        while ((l = r.readLine()) != null) if (!l.startsWith("#")) n++;
        return n;
      }
    }
    JAVA
    javac CountVars.java && java -cp . CountVars "$vcf" "$truth" > summary.txt || echo "evaluation_failed" > summary.txt
    """
}

workflow {
  g = GET_GATK()
  call = CALL(g, params.sample_name, params.ref, params.ref_fai, params.ref_dict, params.cram, params.bed)
  EVALUATE(call, params.truth_vcf)
}

