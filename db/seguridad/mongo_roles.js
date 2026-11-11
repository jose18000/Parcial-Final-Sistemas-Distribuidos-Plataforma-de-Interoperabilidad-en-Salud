// db/seguridad/mongo_roles.js — mínimo privilegio en el MongoDB de la Sede 2 (Cartagena).
//
//   hsb_escritor  rol escritor_sin_borrado: find, insert, update (sin remove ni dropCollection)
//   api_lector    rol solo_lectura: find
//
// Corre al crear la base (docker-entrypoint-initdb.d) y desplegar.sh la reaplica. Idempotente.
const nombreDb = process.env.MONGO_INITDB_DATABASE || 'clinica_cartagena';
const d = db.getSiblingDB(nombreDb);
const todo = { db: nombreDb, collection: '' };
const lectura = ['find', 'listCollections', 'listIndexes', 'collStats', 'dbStats'];

function asegurarRol(nombre, acciones) {
  const def = { privileges: [{ resource: todo, actions: acciones }], roles: [] };
  if (d.getRole(nombre)) d.updateRole(nombre, def); else d.createRole({ role: nombre, ...def });
}
function asegurarUsuario(usuario, clave, rol) {
  if (!clave) throw new Error('Falta la contraseña de ' + usuario);
  const def = { pwd: clave, roles: [{ role: rol, db: nombreDb }] };
  if (d.getUser(usuario)) d.updateUser(usuario, def);
  else d.createUser({ user: usuario, mechanisms: ['SCRAM-SHA-256'], ...def });
}

asegurarRol('escritor_sin_borrado', [...lectura, 'insert', 'update', 'createIndex']);
asegurarRol('solo_lectura', lectura);
asegurarUsuario('hsb_escritor', process.env.HSB_DB_PASSWORD, 'escritor_sin_borrado');
asegurarUsuario('api_lector', process.env.API_DB_PASSWORD, 'solo_lectura');
print('[seguridad] ' + nombreDb + ': hsb_escritor (sin borrado), api_lector (solo lectura)');
