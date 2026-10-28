"""Regressões reais do experimento, incluindo PyArrow e DuckDB, sem mocks de validação."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
import shutil
from types import SimpleNamespace
import compression_stage as C

FIXTURE=C.REPO/'tests/fixtures/bweb/queries.csv'

class TestCompressionStage(unittest.TestCase):
    def test_grid_incompleto_nao_aprova_decisao(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=SimpleNamespace(output=tmp,binary=str(C.REPO/'target/debug/tsepack'),csv=str(FIXTURE),
                 raw_root=str(FIXTURE.parent),manifest=str(C.REPO/'tests/fixtures/origin-v2-good.json'),
                 pack=str(FIXTURE.parent),map=str(C.REPO/'relatorios-locais/etapa-1/mt/map.json'))
            stage=C.Stage(args)
            with self.assertRaisesRegex(ValueError,'grid CSV incompleto'):stage.views_phase()
            self.assertFalse((Path(tmp)/'view-comparison.json').exists())

    def test_chaves_json_repetidas_reprovam_em_vez_de_sobrescrever(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'duplicate.json'
            path.write_text('{"format_version":1,"format_version":1}')
            with self.assertRaisesRegex(ValueError,'duplicada'):C.read_json(path)

    def test_parquet_restaura_multilinhas_zeros_e_duplicatas_e_confere_consultas(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            payload=tmp/'payload.parquet'
            measured=C.parquet_encode(FIXTURE,payload,C.LIMITS['PARQUET_ROW_GROUP_SMALL'],3)
            self.assertTrue(measured['round_trip_ok'])
            binary=C.REPO/'target/debug/tsepack'
            self.assertTrue(binary.exists(),'cargo test deve gerar o executável de integração')
            reference=tmp/'reference.json'
            subprocess.run([str(binary),'queries','--input',str(FIXTURE),'--output',str(reference)],check=True)
            expected=C.read_json(reference)
            self.assertEqual(C.parquet_queries(payload,expected,measured['encoded_sha256']),expected)
            output=tmp/'restored.csv'
            result=C.validate_parquet(payload,measured['source_sha256'],FIXTURE.stat().st_size,3,output)
            self.assertEqual(result['records'],3)
            self.assertEqual(output.read_bytes(),FIXTURE.read_bytes())
            with self.assertRaises(ValueError):C.validate_parquet(payload,C.sha256_file(reference),FIXTURE.stat().st_size,3,tmp/'no.csv')
            self.assertFalse((tmp/'no.csv').exists())

    def test_view_reprova_alteracao_e_campos_desconhecidos_sem_saida(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);payload=tmp/'payload.parquet'
            m=C.parquet_encode(FIXTURE,payload,C.LIMITS['PARQUET_ROW_GROUP_SMALL'],3)
            view={'artifact_kind':'bweb_storage_view','format_version':1,'guarantee':'exact-csv-member-bytes',
                  'kind':'parquet','source':{'bytes':FIXTURE.stat().st_size,'sha256':C.sha256_file(FIXTURE),'records':3,
                  'zip_path':None,'zip_sha256':None,'member_name':None,'member_ordinal':None},
                  'encoded':{'file':payload.name,'bytes':payload.stat().st_size,'sha256':C.sha256_file(payload)},
                  'codec':None,'dictionary':None,'pack_manifest':None,'decoded_stream':None}
            descriptor=tmp/'view.json';C.save(descriptor,view)
            C.restore_view(descriptor,tmp/'good.csv',C.REPO/'target/debug/tsepack')
            self.assertEqual((tmp/'good.csv').read_bytes(),FIXTURE.read_bytes())
            view['unknown']='não ignorar';C.save(descriptor,view)
            with self.assertRaises(ValueError):C.restore_view(descriptor,tmp/'no.csv',C.REPO/'target/debug/tsepack')
            view.pop('unknown');C.save(descriptor,view)
            payload.write_bytes(payload.read_bytes()[:-1])
            with self.assertRaises(ValueError):C.restore_view(descriptor,tmp/'no.csv',C.REPO/'target/debug/tsepack')
            self.assertFalse((tmp/'no.csv').exists())

    def test_particoes_nao_compartilham_secoes_e_totalizam_todas_as_ocorrencias(self):
        row=next(C.logical_rows(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);source=tmp/'synthetic-derived.csv'
            with source.open('wb') as stream:
                stream.write(C.encode_row(C.HEADER,header=True))
                for i in range(40):
                    item=list(row);item[14]=str(i);stream.write(C.encode_row(item))
            report=C.split_dictionary(source,tmp/'split')
            groups={}
            count=0
            for name,part in report['parts'].items():
                groups[name]={tuple(r[i] for i in (5,7,10,11,13,14)) for r in C.logical_rows(part['path'])}
                count+=part['records']
                self.assertEqual(C.sha256_file(part['path']),part['sha256'])
            self.assertEqual(count,40)
            self.assertTrue(all(groups.values()))
            self.assertFalse(groups['train']&groups['validation'] or groups['train']&groups['test'] or groups['test']&groups['validation'])
            self.assertEqual(C.split_dictionary(source,tmp/'split'),report)

    def test_grupos_insuficientes_nao_criam_relatorio_aprovado(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):C.split_dictionary(FIXTURE,tmp)
            self.assertFalse((Path(tmp)/'split.json').exists())

    def test_cache_csv_regenera_do_zip_preservado_sem_exigir_copia_permanente(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);raw=tmp/'raw';raw.mkdir();zip_path=raw/'synthetic.zip'
            with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('bweb.csv',FIXTURE.read_bytes())
            binary=C.REPO/'target/debug/tsepack'
            manifest=tmp/'origin.json'
            subprocess.run([str(binary),'inspect','--input',str(raw),'--manifest',str(manifest)],check=True,stdout=subprocess.DEVNULL)
            bundle=tmp/'bundle';bundle.mkdir()
            archive=bundle/'forensic-mt'
            subprocess.run([str(binary),'optimize','--input',str(raw),'--manifest',str(manifest),'--output',str(archive)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            encoded=tmp/'encoded'
            subprocess.run([str(binary),'codec','compress','--input',str(FIXTURE),'--output',str(encoded),'--method','zstd-3'],check=True,stdout=subprocess.DEVNULL)
            view={'artifact_kind':'bweb_storage_view','format_version':1,'guarantee':'exact-csv-member-bytes','kind':'csv-codec',
                  'source':{'bytes':FIXTURE.stat().st_size,'sha256':C.sha256_file(FIXTURE),'records':3,'zip_path':zip_path.name,
                            'zip_sha256':C.sha256_file(zip_path),'member_name':'bweb.csv','member_ordinal':0},
                  'encoded':{'file':'payload.encoded','bytes':encoded.stat().st_size,'sha256':C.sha256_file(encoded)},
                  'codec':'zstd-3','dictionary':None,'pack_manifest':None,'decoded_stream':None}
            recipe=bundle/'bweb-view-recipe.json';C.save(recipe,view)
            doc={'artifact_kind':'urnapack_local_bundle','format_version':1,
                 'archive_descriptor':dict(C.describe(archive/'dataset.json'),relative_file='forensic-mt/dataset.json'),
                 'bweb_view_recipe':dict(C.describe(recipe),relative_file='bweb-view-recipe.json')}
            C.save(bundle/'bundle.json',doc)
            moved=tmp/'moved-bundle';shutil.copytree(bundle,moved);shutil.rmtree(bundle);shutil.rmtree(raw)
            target=tmp/'materialized';C.materialize_view(moved/'bundle.json',target,binary)
            self.assertEqual(C.sha256_file(target/'payload.encoded'),view['encoded']['sha256'])
            restored=tmp/'restored.csv';C.restore_view(target/'view.json',restored,binary)
            self.assertEqual(restored.read_bytes(),FIXTURE.read_bytes())
            view['encoded']['file']='../escape'
            C.save(moved/'bweb-view-recipe.json',view)
            doc['bweb_view_recipe']=dict(C.describe(moved/'bweb-view-recipe.json'),relative_file='bweb-view-recipe.json')
            C.save(moved/'bundle.json',doc)
            with self.assertRaisesRegex(ValueError,'caminho de objeto inválido'):
                C.materialize_view(moved/'bundle.json',tmp/'bad-output',binary)
            self.assertFalse((tmp/'bad-output').exists())
            self.assertFalse((tmp/'escape').exists())

if __name__=='__main__':unittest.main()
